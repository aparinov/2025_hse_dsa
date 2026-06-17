from __future__ import annotations

import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.projects.embeddings import encode_texts
from apps.projects.models import Project
from apps.projects.services_matching import count_blocking_pairs, run_stable_matching


User = get_user_model()

SYNTHETIC_STUDENT_USERNAME_PREFIX = 'synthetic_student_'


def synthetic_student_index(student: User) -> int | None:
    """Номер когорты из username (1..150), не Django pk."""
    username = student.username or ''
    if not username.startswith(SYNTHETIC_STUDENT_USERNAME_PREFIX):
        return None
    suffix = username[len(SYNTHETIC_STUDENT_USERNAME_PREFIX) :]
    return int(suffix) if suffix.isdigit() else None


def _sort_synthetic_students(students: list[User]) -> list[User]:
    return sorted(students, key=lambda student: synthetic_student_index(student) or 10**9)


SCENARIOS = (
    ('base', 'Base'),
    ('recsys_only', 'RecSys-only'),
    ('recsys_prof_rank', 'RecSys + Prof. Rank'),
    ('hybrid', 'Hybrid'),
    ('stable_matching', 'Stable Matching'),
)

SCENARIO_COLORS = {
    'base': '#4C72B0',
    'recsys_only': '#DD8452',
    'recsys_prof_rank': '#55A868',
    'hybrid': '#C44E52',
    'stable_matching': '#8172B2',
}


@dataclass(frozen=True)
class ExperimentConfig:
    students_limit: int = 150
    projects_limit: int = 100
    top_k: int = 20
    application_k: int = 5
    metrics_k: tuple[int, ...] = (1, 5, 10, 20)
    seed: int = 42
    top_project_share: float = 0.20
    top_demand_share: float = 0.80
    oracle_tag_weight: float = 0.40
    oracle_semantic_weight: float = 0.45
    oracle_gpa_weight: float = 0.15


def _student_profile_text(student: User) -> str:
    parts = []
    bio = (student.bio or '').strip()
    cover_letter = (student.cover_letter or '').strip()
    if bio:
        parts.append(f'bio: {bio}')
    if cover_letter:
        parts.append(f'cover_letter: {cover_letter}')
    if not parts and (student.program or '').strip():
        parts.append(f'program: {student.program.strip()}')
    return ' '.join(parts) if parts else '(профиль не заполнен)'


def load_django_dataset(config: ExperimentConfig) -> tuple[list[User], list[Project]]:
    """
    Студенты: только когорта seed_recommendation_demo (synthetic_student_1..N).
    JSON synthetic_student_profiles.json не читается здесь — он уже должен быть в БД
    после `seed_recommendation_demo --profiles-json ...`.
    Проекты: случайный семпл projects_limit штук (фиксированный seed).
    """
    students = _sort_synthetic_students(
        list(
            User.objects.filter(
                role=User.Role.STUDENT,
                username__startswith=SYNTHETIC_STUDENT_USERNAME_PREFIX,
            ).prefetch_related('interests')
        )
    )[: config.students_limit]

    all_projects = list(
        Project.objects.filter(status=Project.Status.RECRUITMENT).prefetch_related('tags', 'participants')
    )
    if len(all_projects) > config.projects_limit:
        rng = random.Random(config.seed)
        projects = rng.sample(all_projects, config.projects_limit)
        projects.sort(key=lambda project: project.pk)
    else:
        projects = sorted(all_projects, key=lambda project: (project.created_at, project.pk))

    if not students:
        raise RuntimeError(
            'В БД нет synthetic_student_* — выполните seed_recommendation_demo '
            'с --profiles-json src/data/synthetic_student_profiles.json'
        )
    if not projects:
        raise RuntimeError('В БД нужны проекты со статусом RECRUITMENT.')
    return students, projects


def build_ground_truth_prompt(students: list[User], projects: list[Project], limit: int = 50) -> str:
    """Текстовый промпт для внешнего LLM (опционально). Эксперименты используют proxy GT автоматически."""
    batch = _sort_synthetic_students(students)[:limit]
    student_ids = [synthetic_student_index(student) for student in batch]

    student_lines = []
    for student in batch:
        cohort_index = synthetic_student_index(student)
        interests = ', '.join(tag.name for tag in student.interests.all())
        program = (student.program or '').strip() or '—'
        student_lines.append(
            f'- student_id={cohort_index}; program={program}; interests={interests}; {_student_profile_text(student)}'
        )

    project_lines = []
    for project in sorted(projects, key=lambda item: item.pk):
        tags = ', '.join(tag.name for tag in project.tags.all())
        description = (project.description or '').strip() or '—'
        project_lines.append(
            f'- project_id={project.pk}; title={project.title}; tags={tags}; description={description}'
        )

    return f"""Подбери идеальный проект для каждого студента по смысловому соответствию профиля и проекта.
Верни строго JSON-массив без markdown, ровно для student_id: {', '.join(map(str, student_ids))}.
[{{"student_id": <int>, "ideal_project_id": <int>, "reason": "<коротко>"}}]

Студенты:
{chr(10).join(student_lines)}

Проекты:
{chr(10).join(project_lines)}
"""


def save_ground_truth_prompt(path: Path, students: list[User], projects: list[Project], limit: int = 50) -> Path:
    prompt = build_ground_truth_prompt(students, projects, limit=limit)
    path.write_text(prompt, encoding='utf-8')
    return path


def parse_ground_truth_json(text: str, students: Iterable[User] | None = None) -> dict[int, int]:
    payload = text.strip()
    if payload.startswith('```'):
        payload = re.sub(r'^```(?:json)?\s*|\s*```$', '', payload, flags=re.IGNORECASE | re.DOTALL)
    rows = json.loads(payload)
    parsed = {int(row['student_id']): int(row['ideal_project_id']) for row in rows}
    if not students:
        return parsed
    index_to_pk = {
        index: student.pk
        for student in students
        if (index := synthetic_student_index(student)) is not None
    }
    if parsed and all(student_id in index_to_pk for student_id in parsed):
        return {index_to_pk[student_id]: project_id for student_id, project_id in parsed.items()}
    return parsed


def _tokens(value: str) -> Counter:
    return Counter(re.findall(r'[\wа-яА-ЯёЁ]+', (value or '').casefold()))


def _cosine_counts(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm)


def _safe_encode(texts: list[str]) -> Optional[np.ndarray]:
    """Матрица (len(texts), dim); пустые строки -> нулевой вектор (индексы не сдвигаются)."""
    try:
        dim = 384
        vectors = np.zeros((len(texts), dim), dtype=np.float64)
        non_empty = [(index, text) for index, text in enumerate(texts) if (text or '').strip()]
        if not non_empty:
            return vectors
        encoded = encode_texts([text for _, text in non_empty])
        for row, (index, _) in enumerate(non_empty):
            vectors[index] = encoded[row]
        return vectors
    except Exception:
        return None


def _tag_overlap(student: User, project: Project) -> float:
    student_tags = {tag.name.casefold() for tag in student.interests.all()}
    project_tags = {tag.name.casefold() for tag in project.tags.all()}
    if not student_tags or not project_tags:
        return 0.0
    return len(student_tags & project_tags) / len(student_tags | project_tags)


def _gpa_relevance(student: User, project: Project) -> float:
    grades = getattr(student, 'grades_json', None) or {}
    if not isinstance(grades, dict):
        return 0.0
    grades_by_subject = {str(subject).casefold(): float(value) for subject, value in grades.items() if value not in (None, '')}
    subjects = set()
    tag_subjects = getattr(settings, 'PROJECT_TAG_SUBJECTS', {})
    for tag in project.tags.all():
        subjects.update(subject.casefold() for subject in tag_subjects.get(tag.name, ()))
    matched = [grades_by_subject[subject] for subject in subjects if subject in grades_by_subject]
    return (sum(matched) / len(matched) / 10.0) if matched else 0.0


def build_score_matrices(students: list[User], projects: list[Project]) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    student_texts = [
        ' '.join(part for part in (student.cover_letter, student.bio, student.program) if part)
        for student in students
    ]
    student_bios = [student.bio or '' for student in students]
    project_texts = [
        ' '.join([project.title, project.description, ' '.join(tag.name for tag in project.tags.all())])
        for project in projects
    ]
    project_descriptions = [project.description or '' for project in projects]

    rec_embeddings = _safe_encode(student_texts + project_texts)
    teacher_embeddings = _safe_encode(student_bios + project_descriptions)

    rec_scores = np.zeros((len(students), len(projects)), dtype=float)
    prof_scores = np.zeros((len(students), len(projects)), dtype=float)
    components = {
        'tags_overlap': np.zeros((len(students), len(projects)), dtype=float),
        'gpa_rel': np.zeros((len(students), len(projects)), dtype=float),
        'recsys_semantic': np.zeros((len(students), len(projects)), dtype=float),
        'teacher_semantic': np.zeros((len(students), len(projects)), dtype=float),
        'popularity_prior': np.zeros((len(students), len(projects)), dtype=float),
    }
    popularity = np.linspace(1.0, 0.2, len(projects))

    for student_index, student in enumerate(students):
        student_tokens = _tokens(student_texts[student_index])
        bio_tokens = _tokens(student_bios[student_index])
        for project_index, project in enumerate(projects):
            if rec_embeddings is not None:
                semantic = float(np.dot(rec_embeddings[student_index], rec_embeddings[len(students) + project_index]))
            else:
                semantic = _cosine_counts(student_tokens, _tokens(project_texts[project_index]))

            if teacher_embeddings is not None:
                teacher_semantic = float(np.dot(teacher_embeddings[student_index], teacher_embeddings[len(students) + project_index]))
            else:
                teacher_semantic = _cosine_counts(bio_tokens, _tokens(project_descriptions[project_index]))

            tags = _tag_overlap(student, project)
            grades = _gpa_relevance(student, project)
            rec_semantic = max(semantic, 0)
            prof_semantic = max(teacher_semantic, 0)
            components['tags_overlap'][student_index, project_index] = tags
            components['gpa_rel'][student_index, project_index] = grades
            components['recsys_semantic'][student_index, project_index] = rec_semantic
            components['teacher_semantic'][student_index, project_index] = prof_semantic
            components['popularity_prior'][student_index, project_index] = popularity[project_index]
            rec_scores[student_index, project_index] = 0.45 * tags + 0.25 * popularity[project_index] + 0.20 * rec_semantic + 0.10 * grades
            prof_scores[student_index, project_index] = 0.40 * grades + 0.40 * prof_semantic + 0.20 * tags
    return rec_scores, prof_scores, components


def infer_ground_truth(
    students: list[User],
    projects: list[Project],
    components: dict[str, np.ndarray],
    config: ExperimentConfig,
) -> dict[int, int]:
    """
    Контролируемый hidden relevance: без popularity и без capacity.
    Это ближе к "идеальному проекту" студента, чем к текущей RecSys-формуле.
    """
    oracle_scores = (
        config.oracle_tag_weight * components['tags_overlap']
        + config.oracle_semantic_weight * components['recsys_semantic']
        + config.oracle_gpa_weight * components['gpa_rel']
    )
    return {student.pk: projects[int(np.argmax(oracle_scores[index]))].pk for index, student in enumerate(students)}


def _normalize_ground_truth(
    ground_truth: Optional[dict[int, int]],
    students: list[User],
    projects: list[Project],
    fallback_ground_truth: dict[int, int],
) -> dict[int, int]:
    if not ground_truth:
        return fallback_ground_truth

    student_ids = {student.pk for student in students}
    cohort_to_pk = {
        index: student.pk
        for student in students
        if (index := synthetic_student_index(student)) is not None
    }
    project_ids = {project.pk for project in projects}
    normalized = {}
    for raw_student_id, raw_project_id in ground_truth.items():
        student_id = int(raw_student_id)
        project_id = int(raw_project_id)
        if student_id not in student_ids:
            student_id = cohort_to_pk.get(student_id)
        if student_id in student_ids and project_id in project_ids:
            normalized[student_id] = project_id

    return {
        student.pk: normalized.get(student.pk, fallback_ground_truth[student.pk])
        for student in students
    }


def _capacities(projects: list[Project]) -> dict[int, int]:
    return {project.pk: max(1, int(project.max_participants or 1)) for project in projects}


def _top_indices(scores: np.ndarray, k: int) -> list[int]:
    return list(np.argsort(-scores)[:k])


def _full_ranking(scores: np.ndarray) -> list[int]:
    return list(np.argsort(-scores))


def _pareto_project_order(projects: list[Project], config: ExperimentConfig) -> list[int]:
    top_count = max(1, round(len(projects) * config.top_project_share))
    top_weight = config.top_demand_share / top_count
    tail_weight = (1 - config.top_demand_share) / max(1, len(projects) - top_count)
    weights = [top_weight if index < top_count else tail_weight for index in range(len(projects))]
    rng = random.Random(config.seed)
    return [index for index, _ in sorted(enumerate(weights), key=lambda item: (-item[1], rng.random()))]


def _weighted_without_replacement(indices: list[int], weights: list[float], k: int, rng: random.Random) -> list[int]:
    remaining = list(indices)
    remaining_weights = list(weights)
    result = []
    for _ in range(min(k, len(remaining))):
        chosen = rng.choices(range(len(remaining)), weights=remaining_weights, k=1)[0]
        result.append(remaining.pop(chosen))
        remaining_weights.pop(chosen)
    return result


def _greedy_assign(
    students: list[User],
    projects: list[Project],
    preferences: dict[int, list[int]],
    capacities: dict[int, int],
) -> dict[int, int]:
    free_capacity = dict(capacities)
    assignment = {}
    for student in students:
        for project_id in preferences.get(student.pk, []):
            if free_capacity.get(project_id, 0) > 0:
                assignment[student.pk] = project_id
                free_capacity[project_id] -= 1
                break
    return assignment


def _project_preferences(students: list[User], projects: list[Project], prof_scores: np.ndarray) -> dict[int, list[int]]:
    prefs = {}
    for project_index, project in enumerate(projects):
        order = np.argsort(-prof_scores[:, project_index])
        prefs[project.pk] = [students[int(index)].pk for index in order]
    return prefs


def _rerank_gs_first(recsys_prefs: dict[int, list[int]], gs_assignment: dict[int, int]) -> dict[int, list[int]]:
    reranked = {}
    for student_id, recommendations in recsys_prefs.items():
        assigned_project = gs_assignment.get(student_id)
        if assigned_project:
            reranked[student_id] = [assigned_project] + [
                project_id for project_id in recommendations if project_id != assigned_project
            ]
        else:
            reranked[student_id] = list(recommendations)
    return reranked


def _rerank_by_professor_acceptance(
    students: list[User],
    projects: list[Project],
    recsys_prefs: dict[int, list[int]],
    rec_scores: np.ndarray,
    prof_scores: np.ndarray,
    recsys_weight: float = 0.65,
    professor_weight: float = 0.35,
) -> dict[int, list[int]]:
    """Effective list for scenario 3: RecSys candidates, adjusted by professor-side fit."""
    project_id_to_index = {project.pk: index for index, project in enumerate(projects)}
    reranked = {}
    for student_index, student in enumerate(students):
        prefs = recsys_prefs[student.pk]
        scored = []
        for position, project_id in enumerate(prefs):
            project_index = project_id_to_index[project_id]
            score = (
                recsys_weight * rec_scores[student_index, project_index]
                + professor_weight * prof_scores[student_index, project_index]
            )
            scored.append((-score, position, project_id))
        reranked[student.pk] = [project_id for _, _, project_id in sorted(scored)]
    return reranked


def _metrics(
    scenario_id: str,
    scenario_name: str,
    students: list[User],
    capacities: dict[int, int],
    assignment: dict[int, int],
    preferences: dict[int, list[int]],
    project_prefs: dict[int, list[int]],
    ground_truth: dict[int, int],
    metrics_k: tuple[int, ...],
    assignment_preference_source: dict[int, list[int]] | None = None,
    stability_preferences: dict[int, list[int]] | None = None,
) -> dict:
    assignment_preference_source = assignment_preference_source or preferences
    stability_preferences = stability_preferences or preferences
    row = {'scenario_id': scenario_id, 'scenario_name': scenario_name}
    for k in metrics_k:
        hits = 0
        dcg = 0.0
        for student in students:
            top = preferences.get(student.pk, [])[:k]
            ideal = ground_truth.get(student.pk)
            if ideal in top:
                rank = top.index(ideal) + 1
                hits += 1
                dcg += 1 / math.log2(rank + 1)
        row[f'hit_rate_at_{k}'] = round(hits / len(students), 4)
        row[f'ndcg_at_{k}'] = round(dcg / len(students), 4)

    total_capacity = sum(capacities.values())
    assigned_project_counts = Counter(assignment.values())
    assigned_ranks = []
    reciprocal_ranks = []
    for student in students:
        assigned_project = assignment.get(student.pk)
        if not assigned_project:
            continue
        ranking = assignment_preference_source.get(student.pk, [])
        if assigned_project in ranking:
            rank = ranking.index(assigned_project) + 1
            assigned_ranks.append(rank)
            reciprocal_ranks.append(1 / rank)

    row['assigned_pct'] = round(len(assignment) / len(students) * 100, 2)
    row['unassigned_students'] = len(students) - len(assignment)
    row['capacity_utilization_pct'] = round(len(assignment) / total_capacity * 100, 2) if total_capacity else 0.0
    row['filled_projects_pct'] = round(
        sum(1 for project_id, capacity in capacities.items() if assigned_project_counts[project_id] >= capacity)
        / len(capacities)
        * 100,
        2,
    )
    row['mean_student_rank_assigned'] = round(sum(assigned_ranks) / len(assigned_ranks), 2) if assigned_ranks else 0.0
    row['mrr_assigned'] = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0
    row['blocking_pairs'] = count_blocking_pairs(
        assignment,
        capacities,
        stability_preferences,
        project_prefs,
        students,
    )
    return row


def run_experiments(
    students: list[User],
    projects: list[Project],
    config: Optional[ExperimentConfig] = None,
    ground_truth: Optional[dict[int, int]] = None,
) -> tuple[
    list[dict],
    list[dict],
    dict[str, dict[str, Counter]],
    dict[str, dict[int, list[int]]],
    dict[str, dict[int, int]],
    dict[str, dict[int, list[int]]],
    np.ndarray,
    np.ndarray,
    dict[str, np.ndarray],
    dict[int, int],
]:
    config = config or ExperimentConfig()
    rec_scores, prof_scores, components = build_score_matrices(students, projects)
    inferred_ground_truth = infer_ground_truth(students, projects, components, config)
    ground_truth = _normalize_ground_truth(ground_truth, students, projects, inferred_ground_truth)
    capacities = _capacities(projects)
    project_prefs = _project_preferences(students, projects, prof_scores)
    project_ids = [project.pk for project in projects]
    project_id_to_index = {project_id: index for index, project_id in enumerate(project_ids)}
    rng = random.Random(config.seed)

    pareto_order = _pareto_project_order(projects, config)
    top_count = max(1, round(len(projects) * config.top_project_share))
    pareto_weights = [config.top_demand_share / top_count if idx < top_count else (1 - config.top_demand_share) / max(1, len(projects) - top_count) for idx in range(len(projects))]
    ordered_pareto_weights = [pareto_weights[index] for index in pareto_order]

    scenario_preferences = {}
    scenario_preferences['base'] = {
        student.pk: [
            project_ids[index]
            for index in _weighted_without_replacement(pareto_order, ordered_pareto_weights, config.top_k, rng)
        ]
        for student in students
    }
    scenario_preferences['recsys_only'] = {
        student.pk: [project_ids[index] for index in _full_ranking(rec_scores[row])[: config.top_k]]
        for row, student in enumerate(students)
    }
    scenario_preferences['recsys_prof_rank'] = _rerank_by_professor_acceptance(
        students,
        projects,
        scenario_preferences['recsys_only'],
        rec_scores,
        prof_scores,
    )
    scenario_preferences['stable_matching'] = scenario_preferences['recsys_only']
    application_preferences = {
        scenario_id: {
            student_id: prefs[: config.application_k]
            for student_id, prefs in preferences.items()
        }
        for scenario_id, preferences in scenario_preferences.items()
    }
    application_preferences['recsys_prof_rank'] = {
        student_id: prefs[: config.application_k]
        for student_id, prefs in scenario_preferences['recsys_only'].items()
    }

    assignments = {
        'base': _greedy_assign(
            students,
            projects,
            application_preferences['base'],
            capacities,
        ),
        'recsys_only': _greedy_assign(
            students,
            projects,
            application_preferences['recsys_only'],
            capacities,
        ),
    }

    prof_rank_assignment = {}
    occupied = Counter()
    candidates = []
    for student_index, student in enumerate(students):
        for project_id in application_preferences['recsys_prof_rank'][student.pk]:
            project_index = project_id_to_index[project_id]
            candidates.append((-prof_scores[student_index, project_index], student.pk, project_id))
    for _, student_id, project_id in sorted(candidates):
        if student_id not in prof_rank_assignment and occupied[project_id] < capacities[project_id]:
            prof_rank_assignment[student_id] = project_id
            occupied[project_id] += 1
    assignments['recsys_prof_rank'] = prof_rank_assignment
    assignments['stable_matching'] = run_stable_matching(
        students=students,
        projects=projects,
        capacities=capacities,
        student_prefs=application_preferences['stable_matching'],
        project_prefs=project_prefs,
    )
    scenario_preferences['hybrid'] = _rerank_gs_first(
        scenario_preferences['recsys_only'],
        assignments['stable_matching'],
    )
    application_preferences['hybrid'] = {
        student_id: prefs[: config.application_k]
        for student_id, prefs in scenario_preferences['hybrid'].items()
    }
    assignments['hybrid'] = _greedy_assign(
        students,
        projects,
        application_preferences['hybrid'],
        capacities,
    )

    metrics = []
    assignment_rows = []
    histograms = {'first_choice': {}, 'assignments': {}}
    for scenario_id, scenario_name in SCENARIOS:
        ranking_prefs = scenario_preferences[scenario_id]
        application_prefs = application_preferences[scenario_id]
        assignment = assignments[scenario_id]
        metrics.append(
            _metrics(
                scenario_id,
                scenario_name,
                students,
                capacities,
                assignment,
                ranking_prefs,
                project_prefs,
                ground_truth,
                config.metrics_k,
                scenario_preferences['recsys_only'],
                application_prefs,
            )
        )
        histograms['first_choice'][scenario_id] = Counter(
            ranking_prefs[student.pk][0]
            for student in students
            if ranking_prefs.get(student.pk)
        )
        histograms['assignments'][scenario_id] = Counter(assignment.values())
        for student in students:
            assigned_project_id = assignment.get(student.pk, '')
            assignment_rows.append(
                {
                    'student_id': student.pk,
                    'project_id': assigned_project_id,
                    'assigned_status': 'assigned' if assigned_project_id else 'unassigned',
                    'scenario_id': scenario_id,
                    'assigned_rank_in_recsys': (
                        scenario_preferences['recsys_only'][student.pk].index(assigned_project_id) + 1
                        if assigned_project_id in scenario_preferences['recsys_only'][student.pk]
                        else ''
                    ),
                }
            )
    return (
        metrics,
        assignment_rows,
        histograms,
        scenario_preferences,
        assignments,
        application_preferences,
        rec_scores,
        prof_scores,
        components,
        ground_truth,
    )


def save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _preference_rows(
    preferences_by_scenario: dict[str, dict[int, list[int]]],
    owner_column: str,
    item_column: str,
) -> list[dict]:
    rows = []
    for scenario_id, preferences in preferences_by_scenario.items():
        for owner_id, item_ids in sorted(preferences.items()):
            for rank, item_id in enumerate(item_ids, start=1):
                rows.append(
                    {
                        'scenario_id': scenario_id,
                        owner_column: owner_id,
                        'rank': rank,
                        item_column: item_id,
                    }
                )
    return rows


def _ground_truth_rows(ground_truth: dict[int, int]) -> list[dict]:
    return [
        {'student_id': student_id, 'ideal_project_id': project_id}
        for student_id, project_id in sorted(ground_truth.items())
    ]


HISTOGRAM_TOP_PROJECTS = 35


def _recsys_project_order(histograms: dict[str, dict[str, Counter]], limit: int = HISTOGRAM_TOP_PROJECTS) -> list[int]:
    counter = histograms['first_choice']['recsys_only']
    return [project_id for project_id, _ in counter.most_common()][:limit]


def _plot_demand_concentration(axis, histograms: dict[str, dict[str, Counter]]) -> None:
    project_order = _recsys_project_order(histograms)
    x = np.arange(1, len(project_order) + 1)
    for scenario_id, label in (
        ('recsys_only', 'RecSys-only'),
        ('base', 'Base (без ML)'),
    ):
        counter = histograms['first_choice'][scenario_id]
        axis.plot(
            x,
            [counter.get(project_id, 0) for project_id in project_order],
            label=label,
            color=SCENARIO_COLORS[scenario_id],
            linewidth=2,
            marker='o',
            markersize=3,
        )
    axis.set_title('RecSys стягивает студентов к одним и тем же проектам')
    axis.set_xlabel('проекты (ранг по популярности в RecSys)')
    axis.set_ylabel('студентов с 1-м выбором')
    axis.legend()
    axis.grid(axis='y', alpha=0.25)


def _plot_assignment_comparison(axis, histograms: dict[str, dict[str, Counter]]) -> None:
    project_order = _recsys_project_order(histograms)
    x = np.arange(1, len(project_order) + 1)
    recsys_demand = histograms['first_choice']['recsys_only']
    demand = [recsys_demand.get(project_id, 0) for project_id in project_order]
    recsys_assign = [
        histograms['assignments']['recsys_only'].get(project_id, 0) for project_id in project_order
    ]
    stable_assign = [
        histograms['assignments']['stable_matching'].get(project_id, 0) for project_id in project_order
    ]
    axis.plot(x, demand, label='Спрос (1-я рекомендация RecSys)', color='#DD8452', linewidth=2.5)
    axis.plot(
        x,
        recsys_assign,
        label='Назначения RecSys-only',
        color='#DD8452',
        linewidth=2,
        linestyle='--',
    )
    axis.plot(
        x,
        stable_assign,
        label='Stable Matching',
        color=SCENARIO_COLORS['stable_matching'],
        linewidth=2.5,
    )
    axis.set_title('Stable Matching сглаживает перегруз популярных проектов')
    axis.set_xlabel('проекты (ранг по популярности в RecSys)')
    axis.set_ylabel('студентов')
    axis.legend()
    axis.grid(axis='y', alpha=0.25)


def build_demand_concentration_figure(histograms: dict[str, dict[str, Counter]]):
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 4.5))
    _plot_demand_concentration(axis, histograms)
    figure.tight_layout()
    return figure


def build_assignment_comparison_figure(histograms: dict[str, dict[str, Counter]]):
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 4.5))
    _plot_assignment_comparison(axis, histograms)
    figure.tight_layout()
    return figure


def build_histograms_figure(histograms: dict[str, dict[str, Counter]]):
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 1, figsize=(10, 9))
    _plot_demand_concentration(axes[0], histograms)
    _plot_assignment_comparison(axes[1], histograms)
    figure.tight_layout()
    return figure


def build_metrics_figure(metrics: list[dict]):
    import matplotlib.pyplot as plt

    scenario_names = [row['scenario_name'] for row in metrics]
    figure, axes = plt.subplots(2, 3, figsize=(14, 7))
    axes = axes.ravel()

    chart_specs = (
        ('assigned_pct', 'Assigned, %'),
        ('unassigned_students', 'Unassigned students'),
        ('capacity_utilization_pct', 'Capacity util., %'),
        ('filled_projects_pct', 'Filled projects, %'),
        ('mean_student_rank_assigned', 'Mean assigned rank'),
        ('blocking_pairs', 'Blocking pairs'),
    )
    x_positions = range(len(scenario_names))
    bar_colors = [SCENARIO_COLORS.get(row['scenario_id'], '#888888') for row in metrics]
    for axis, (metric_key, title) in zip(axes, chart_specs):
        values = [row[metric_key] for row in metrics]
        axis.bar(x_positions, values, color=bar_colors)
        axis.set_title(title)
        axis.set_xticks(list(x_positions), scenario_names, rotation=25, ha='right')
    figure.suptitle('Метрики по сценариям', y=1.02)
    figure.tight_layout()
    return figure


def build_recsys_metrics_figure(metrics: list[dict]):
    import matplotlib.pyplot as plt

    k_values = [1, 5, 10, 20]
    x_positions = np.arange(len(k_values))
    n_scenarios = len(metrics)
    width = 0.8 / max(n_scenarios, 1)
    figure, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    for axis, metric_prefix, title in (
        (axes[0], 'hit_rate_at', 'HitRate@K'),
        (axes[1], 'ndcg_at', 'NDCG@K'),
    ):
        for offset, row in enumerate(metrics):
            values = [row.get(f'{metric_prefix}_{k}', 0.0) for k in k_values]
            scenario_id = row['scenario_id']
            axis.bar(
                x_positions + (offset - (n_scenarios - 1) / 2) * width,
                values,
                width=width,
                label=row['scenario_name'],
                color=SCENARIO_COLORS.get(scenario_id, '#888888'),
            )
        axis.set_title(title)
        axis.set_xticks(x_positions, [f'@{k}' for k in k_values])
        axis.legend(loc='upper right', fontsize=8)
    figure.suptitle('Рекомендательные метрики по горизонтам K', y=1.02)
    figure.tight_layout()
    return figure


def show_experiment_plots(metrics: list[dict], histograms: dict[str, dict[str, Counter]]) -> None:
    import matplotlib.pyplot as plt

    build_demand_concentration_figure(histograms)
    build_assignment_comparison_figure(histograms)
    build_recsys_metrics_figure(metrics)
    build_metrics_figure(metrics)
    plt.show()


def _save_figure(path_png: Path, path_pdf: Path, figure) -> None:
    import matplotlib.pyplot as plt

    figure.savefig(path_png, dpi=180, bbox_inches='tight')
    figure.savefig(path_pdf, bbox_inches='tight')
    plt.close(figure)


def save_histograms(materials_dir: Path, histograms: dict[str, dict[str, Counter]]) -> None:
    _save_figure(
        materials_dir / 'first_choice_histograms.png',
        materials_dir / 'first_choice_histograms.pdf',
        build_demand_concentration_figure(histograms),
    )
    _save_figure(
        materials_dir / 'assignment_histograms.png',
        materials_dir / 'assignment_histograms.pdf',
        build_assignment_comparison_figure(histograms),
    )
    _save_figure(
        materials_dir / 'histograms.png',
        materials_dir / 'histograms.pdf',
        build_histograms_figure(histograms),
    )


def save_metrics_charts(path_png: Path, path_pdf: Path, metrics: list[dict]) -> None:
    import matplotlib.pyplot as plt

    figure = build_metrics_figure(metrics)
    figure.savefig(path_png, dpi=180, bbox_inches='tight')
    figure.savefig(path_pdf, bbox_inches='tight')
    plt.close(figure)


def save_recsys_metrics_charts(path_png: Path, path_pdf: Path, metrics: list[dict]) -> None:
    import matplotlib.pyplot as plt

    figure = build_recsys_metrics_figure(metrics)
    figure.savefig(path_png, dpi=180, bbox_inches='tight')
    figure.savefig(path_pdf, bbox_inches='tight')
    plt.close(figure)


def _score_breakdown(
    student_index: int,
    project_index: int,
    rec_scores: np.ndarray,
    prof_scores: np.ndarray,
    components: dict[str, np.ndarray],
) -> str:
    return (
        f"RecSys={rec_scores[student_index, project_index]:.3f}, "
        f"ProfScore={prof_scores[student_index, project_index]:.3f}, "
        f"tags={components['tags_overlap'][student_index, project_index]:.3f}, "
        f"gpa={components['gpa_rel'][student_index, project_index]:.3f}, "
        f"sem_rec={components['recsys_semantic'][student_index, project_index]:.3f}, "
        f"sem_prof={components['teacher_semantic'][student_index, project_index]:.3f}"
    )


def write_cases(
    path: Path,
    students: list[User],
    projects: list[Project],
    scenario_preferences: dict[str, dict[int, list[int]]],
    assignments: dict[str, dict[int, int]],
    rec_scores: np.ndarray,
    prof_scores: np.ndarray,
    components: dict[str, np.ndarray],
) -> None:
    project_titles = {project.pk: project.title for project in projects}
    project_id_to_index = {project.pk: index for index, project in enumerate(projects)}
    student_id_to_index = {student.pk: index for index, student in enumerate(students)}
    lines = ['# Cases', '']

    def recsys_rank(student_id: int, project_id: int | str | None) -> int | None:
        if not project_id:
            return None
        prefs = scenario_preferences['recsys_only'].get(student_id, [])
        return prefs.index(project_id) + 1 if project_id in prefs else None

    scored_students = []
    for student in students:
        rec_project = assignments['recsys_only'].get(student.pk)
        gs_project = assignments['stable_matching'].get(student.pk)
        hybrid_project = assignments['hybrid'].get(student.pk)
        if rec_project == gs_project == hybrid_project:
            continue
        rec_rank = recsys_rank(student.pk, rec_project) or 99
        gs_rank = recsys_rank(student.pk, gs_project) or 99
        hybrid_rank = recsys_rank(student.pk, hybrid_project) or 99
        shift = max(abs(gs_rank - rec_rank), abs(hybrid_rank - rec_rank))
        if not gs_project:
            shift += 10
        scored_students.append((shift, student.pk, student))

    for _, _, student in sorted(scored_students, reverse=True)[:3]:
        student_index = student_id_to_index[student.pk]
        rec_project = assignments['recsys_only'].get(student.pk)
        hybrid_project = assignments['hybrid'].get(student.pk)
        gs_project = assignments['stable_matching'].get(student.pk)
        grades = getattr(student, 'grades_json', {}) or {}
        interests = ', '.join(tag.name for tag in student.interests.all()) or 'нет тегов'

        lines.extend(
            [
                f'## Студент ID {student.pk} / cohort {synthetic_student_index(student)}',
                '',
                f'**Интересы:** {interests}',
                '',
                f'**Предметы и оценки:** {json.dumps(grades, ensure_ascii=False)}',
                '',
                f'**Bio:** {(student.bio or "").strip()[:700] or "не заполнено"}',
                '',
                f'- RecSys-only assignment: {project_titles.get(rec_project, "не распределен")} '
                f'(rank={recsys_rank(student.pk, rec_project) or "—"})',
                f'- Hybrid GS-first assignment: {project_titles.get(hybrid_project, "не распределен")} '
                f'(rank={recsys_rank(student.pk, hybrid_project) or "—"})',
                f'- Stable Matching assignment: {project_titles.get(gs_project, "не распределен")} '
                f'(rank={recsys_rank(student.pk, gs_project) or "—"})',
                '',
            ]
        )

        for label, project_id in (
            ('RecSys-only', rec_project),
            ('Hybrid', hybrid_project),
            ('Stable Matching', gs_project),
        ):
            if not project_id:
                lines.append(f'- {label}: студент остался нераспределен.')
                continue
            project_index = project_id_to_index[project_id]
            lines.append(
                f'- {label} score components for "{project_titles[project_id]}": '
                f'{_score_breakdown(student_index, project_index, rec_scores, prof_scores, components)}.'
            )
        lines.append('')

    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def save_all_artifacts(
    materials_dir: Path,
    config: Optional[ExperimentConfig] = None,
    ground_truth: Optional[dict[int, int]] = None,
    show_plots: bool = False,
) -> tuple[list[dict], dict[str, dict[str, Counter]]]:
    config = config or ExperimentConfig()
    students, projects = load_django_dataset(config)
    (
        metrics,
        assignment_rows,
        histograms,
        scenario_preferences,
        assignments,
        application_preferences,
        rec_scores,
        prof_scores,
        components,
        _ground_truth,
    ) = run_experiments(students, projects, config, ground_truth)
    materials_dir.mkdir(parents=True, exist_ok=True)
    save_csv(materials_dir / 'results_table.csv', metrics)
    save_csv(materials_dir / 'scenario_assignments.csv', assignment_rows)
    save_csv(
        materials_dir / 'scenario_preferences.csv',
        _preference_rows(scenario_preferences, 'student_id', 'project_id'),
    )
    save_csv(
        materials_dir / 'application_preferences.csv',
        _preference_rows(application_preferences, 'student_id', 'project_id'),
    )
    save_csv(
        materials_dir / 'project_preferences.csv',
        _preference_rows(
            {'teacher_rank': _project_preferences(students, projects, prof_scores)},
            'project_id',
            'student_id',
        ),
    )
    save_csv(materials_dir / 'ground_truth.csv', _ground_truth_rows(_ground_truth))
    save_histograms(materials_dir, histograms)
    save_metrics_charts(materials_dir / 'metrics_charts.png', materials_dir / 'metrics_charts.pdf', metrics)
    save_recsys_metrics_charts(
        materials_dir / 'recsys_metrics_charts.png',
        materials_dir / 'recsys_metrics_charts.pdf',
        metrics,
    )
    write_cases(
        materials_dir / 'cases.md',
        students,
        projects,
        scenario_preferences,
        assignments,
        rec_scores,
        prof_scores,
        components,
    )
    if show_plots:
        show_experiment_plots(metrics, histograms)
    return metrics, histograms
