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


@dataclass(frozen=True)
class ExperimentConfig:
    students_limit: int = 150
    projects_limit: int = 100
    top_k: int = 5
    seed: int = 42
    top_project_share: float = 0.20
    top_demand_share: float = 0.80
    hybrid_recsys_weight: float = 0.65


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


def build_score_matrices(students: list[User], projects: list[Project]) -> tuple[np.ndarray, np.ndarray]:
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
            rec_scores[student_index, project_index] = 0.45 * tags + 0.25 * popularity[project_index] + 0.20 * max(semantic, 0) + 0.10 * grades
            prof_scores[student_index, project_index] = 0.40 * grades + 0.40 * max(teacher_semantic, 0) + 0.20 * tags
    return rec_scores, prof_scores


def infer_ground_truth(students: list[User], projects: list[Project], rec_scores: np.ndarray, prof_scores: np.ndarray) -> dict[int, int]:
    total = 0.70 * rec_scores + 0.30 * prof_scores
    return {student.pk: projects[int(np.argmax(total[index]))].pk for index, student in enumerate(students)}


def _capacities(projects: list[Project]) -> dict[int, int]:
    return {project.pk: max(1, int(project.max_participants or 1)) for project in projects}


def _top_indices(scores: np.ndarray, k: int) -> list[int]:
    return list(np.argsort(-scores)[:k])


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


def _metrics(
    scenario_id: str,
    scenario_name: str,
    students: list[User],
    capacities: dict[int, int],
    assignment: dict[int, int],
    preferences: dict[int, list[int]],
    project_prefs: dict[int, list[int]],
    ground_truth: dict[int, int],
    k: int,
) -> dict:
    hits = 0
    dcg = 0.0
    for student in students:
        top = preferences.get(student.pk, [])[:k]
        ideal = ground_truth.get(student.pk)
        if ideal in top:
            rank = top.index(ideal) + 1
            hits += 1
            dcg += 1 / math.log2(rank + 1)
    total_capacity = sum(capacities.values())
    return {
        'scenario_id': scenario_id,
        'scenario_name': scenario_name,
        'hit_rate_at_5': round(hits / len(students), 4),
        'ndcg_at_5': round(dcg / len(students), 4),
        'assigned_pct': round(len(assignment) / len(students) * 100, 2),
        'capacity_utilization_pct': round(len(assignment) / total_capacity * 100, 2) if total_capacity else 0.0,
        'blocking_pairs': count_blocking_pairs(assignment, capacities, preferences, project_prefs, students),
    }


def run_experiments(
    students: list[User],
    projects: list[Project],
    config: Optional[ExperimentConfig] = None,
    ground_truth: Optional[dict[int, int]] = None,
) -> tuple[list[dict], list[dict], dict[str, Counter]]:
    config = config or ExperimentConfig()
    rec_scores, prof_scores = build_score_matrices(students, projects)
    ground_truth = ground_truth or infer_ground_truth(students, projects, rec_scores, prof_scores)
    capacities = _capacities(projects)
    project_prefs = _project_preferences(students, projects, prof_scores)
    project_ids = [project.pk for project in projects]
    rng = random.Random(config.seed)

    pareto_order = _pareto_project_order(projects, config)
    top_count = max(1, round(len(projects) * config.top_project_share))
    pareto_weights = [config.top_demand_share / top_count if idx < top_count else (1 - config.top_demand_share) / max(1, len(projects) - top_count) for idx in range(len(projects))]

    scenario_preferences = {}
    scenario_preferences['base'] = {
        student.pk: [project_ids[index] for index in _weighted_without_replacement(pareto_order, pareto_weights, config.top_k, rng)]
        for student in students
    }
    scenario_preferences['recsys_only'] = {
        student.pk: [project_ids[index] for index in _top_indices(rec_scores[row], config.top_k)]
        for row, student in enumerate(students)
    }
    scenario_preferences['recsys_prof_rank'] = scenario_preferences['recsys_only']
    hybrid_scores = config.hybrid_recsys_weight * rec_scores + (1 - config.hybrid_recsys_weight) * prof_scores
    scenario_preferences['hybrid'] = {
        student.pk: [project_ids[index] for index in _top_indices(hybrid_scores[row], config.top_k)]
        for row, student in enumerate(students)
    }
    scenario_preferences['stable_matching'] = scenario_preferences['recsys_only']

    assignments = {
        'base': _greedy_assign(students, projects, scenario_preferences['base'], capacities),
        'recsys_only': _greedy_assign(students, projects, scenario_preferences['recsys_only'], capacities),
        'hybrid': _greedy_assign(students, projects, scenario_preferences['hybrid'], capacities),
    }

    prof_rank_assignment = {}
    occupied = Counter()
    candidates = []
    for student_index, student in enumerate(students):
        for project_id in scenario_preferences['recsys_prof_rank'][student.pk]:
            project_index = project_ids.index(project_id)
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
        student_prefs=scenario_preferences['stable_matching'],
        project_prefs=project_prefs,
    )

    metrics = []
    assignment_rows = []
    demand_histograms = {}
    for scenario_id, scenario_name in SCENARIOS:
        prefs = scenario_preferences[scenario_id]
        assignment = assignments[scenario_id]
        metrics.append(_metrics(scenario_id, scenario_name, students, capacities, assignment, prefs, project_prefs, ground_truth, config.top_k))
        demand_histograms[scenario_id] = Counter(project_id for values in prefs.values() for project_id in values)
        for student in students:
            assignment_rows.append(
                {
                    'student_id': student.pk,
                    'project_id': assignment.get(student.pk, ''),
                    'assigned_status': 'assigned' if student.pk in assignment else 'unassigned',
                    'scenario_id': scenario_id,
                }
            )
    return metrics, assignment_rows, demand_histograms


def save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_demand_histogram_figure(demand_histograms: dict[str, Counter]):
    import matplotlib.pyplot as plt

    labels = [(scenario_id, title) for scenario_id, title in SCENARIOS]
    figure, axes = plt.subplots(1, len(labels), figsize=(4 * len(labels), 4), sharey=True)
    if len(labels) == 1:
        axes = [axes]
    for axis, (scenario_id, title) in zip(axes, labels):
        values = sorted(demand_histograms[scenario_id].values(), reverse=True)
        axis.bar(range(1, len(values) + 1), values, color='#4C72B0')
        axis.set_title(title)
        axis.set_xlabel('projects by demand rank')
    axes[0].set_ylabel('top-K mentions count')
    figure.suptitle('Распределение спроса на проекты по сценариям', y=1.02)
    figure.tight_layout()
    return figure


def build_metrics_figure(metrics: list[dict]):
    import matplotlib.pyplot as plt

    scenario_names = [row['scenario_name'] for row in metrics]
    figure, axes = plt.subplots(2, 3, figsize=(14, 7))
    axes = axes.ravel()

    chart_specs = (
        ('hit_rate_at_5', 'HitRate@5', '#55A868'),
        ('ndcg_at_5', 'NDCG@5', '#4C72B0'),
        ('assigned_pct', 'Assigned, %', '#C44E52'),
        ('capacity_utilization_pct', 'Capacity util., %', '#8172B2'),
        ('blocking_pairs', 'Blocking pairs', '#CCB974'),
    )
    x_positions = range(len(scenario_names))
    for axis, (metric_key, title, color) in zip(axes, chart_specs):
        values = [row[metric_key] for row in metrics]
        axis.bar(x_positions, values, color=color)
        axis.set_title(title)
        axis.set_xticks(list(x_positions), scenario_names, rotation=25, ha='right')
    axes[-1].axis('off')
    figure.suptitle('Метрики по сценариям', y=1.02)
    figure.tight_layout()
    return figure


def show_experiment_plots(metrics: list[dict], demand_histograms: dict[str, Counter]) -> None:
    import matplotlib.pyplot as plt

    build_demand_histogram_figure(demand_histograms)
    build_metrics_figure(metrics)
    plt.show()


def save_histograms(path_png: Path, path_pdf: Path, demand_histograms: dict[str, Counter]) -> None:
    import matplotlib.pyplot as plt

    figure = build_demand_histogram_figure(demand_histograms)
    figure.savefig(path_png, dpi=180, bbox_inches='tight')
    figure.savefig(path_pdf, bbox_inches='tight')
    plt.close(figure)


def save_metrics_charts(path_png: Path, path_pdf: Path, metrics: list[dict]) -> None:
    import matplotlib.pyplot as plt

    figure = build_metrics_figure(metrics)
    figure.savefig(path_png, dpi=180, bbox_inches='tight')
    figure.savefig(path_pdf, bbox_inches='tight')
    plt.close(figure)


def write_cases(path: Path, students: list[User], projects: list[Project], assignment_rows: list[dict]) -> None:
    by_scenario = defaultdict(dict)
    for row in assignment_rows:
        by_scenario[row['scenario_id']][row['student_id']] = row['project_id']
    project_titles = {project.pk: project.title for project in projects}
    lines = ['# Cases', '']
    changed = [
        student for student in students
        if by_scenario['recsys_only'].get(student.pk) != by_scenario['stable_matching'].get(student.pk)
    ][:3]
    for student in changed:
        rec_project = by_scenario['recsys_only'].get(student.pk)
        gs_project = by_scenario['stable_matching'].get(student.pk)
        lines.append(
            f'- Студент ID {student.pk}. В RecSys-only попадал в проект '
            f'"{project_titles.get(rec_project, rec_project)}", а в Stable Matching был распределен в '
            f'"{project_titles.get(gs_project, gs_project)}": первый проект оказался конкурентным по преподавательскому рангу и capacity.'
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def save_all_artifacts(
    materials_dir: Path,
    config: Optional[ExperimentConfig] = None,
    ground_truth: Optional[dict[int, int]] = None,
    show_plots: bool = False,
) -> tuple[list[dict], dict[str, Counter]]:
    config = config or ExperimentConfig()
    students, projects = load_django_dataset(config)
    metrics, assignment_rows, demand_histograms = run_experiments(students, projects, config, ground_truth)
    materials_dir.mkdir(parents=True, exist_ok=True)
    save_csv(materials_dir / 'results_table.csv', metrics)
    save_csv(materials_dir / 'scenario_assignments.csv', assignment_rows)
    save_histograms(materials_dir / 'histograms.png', materials_dir / 'histograms.pdf', demand_histograms)
    save_metrics_charts(materials_dir / 'metrics_charts.png', materials_dir / 'metrics_charts.pdf', metrics)
    write_cases(materials_dir / 'cases.md', students, projects, assignment_rows)
    if show_plots:
        show_experiment_plots(metrics, demand_histograms)
    return metrics, demand_histograms
