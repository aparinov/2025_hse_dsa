"""Скоринг преподавателя и стабильное распределение студентов по проектам."""
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from typing import Optional

from apps.projects.models import Application, Project

from .embeddings import encode_texts
from .services import _normalize_text

User = get_user_model()

TEACHER_GPA_WEIGHT = 0.4
TEACHER_SEMANTIC_WEIGHT = 0.4
TEACHER_TAGS_WEIGHT = 0.2
MISSING_RANK = 10**9


def _object_id(value) -> int:
    return int(getattr(value, 'pk', value))


def _object_map(values: Iterable) -> dict[int, object]:
    return {_object_id(value): value for value in values}


def _student_tie_key(student_id: int, students_by_id: Optional[Mapping[int, object]] = None) -> tuple:
    student = (students_by_id or {}).get(student_id)
    return (
        getattr(student, 'date_joined', None) is None,
        getattr(student, 'date_joined', None),
        student_id,
    )


def _project_tie_key(project_id: int, projects_by_id: Optional[Mapping[int, object]] = None) -> tuple:
    project = (projects_by_id or {}).get(project_id)
    return (
        getattr(project, 'created_at', None) is None,
        getattr(project, 'created_at', None),
        project_id,
    )


def _normalize_preferences(raw_preferences: Mapping[int, Sequence]) -> dict[int, list[int]]:
    normalized: dict[int, list[int]] = {}
    for owner_id, preferences in raw_preferences.items():
        normalized[int(owner_id)] = [_object_id(item) for item in preferences]
    return normalized


def _normalize_project_preferences(
    raw_preferences: Mapping[int, Sequence | Mapping],
    students_by_id: Optional[Mapping[int, object]] = None,
) -> dict[int, list[int]]:
    normalized: dict[int, list[int]] = {}
    for project_id, preferences in raw_preferences.items():
        if isinstance(preferences, Mapping):
            items = preferences.items()
        else:
            items = enumerate(preferences)

        scored_students = []
        for position, item in items:
            if isinstance(preferences, Mapping):
                student, score = position, item
            elif isinstance(item, tuple) and len(item) == 2:
                student, score = item[0], item[1]
            else:
                student, score = item, None

            student_id = _object_id(student)
            primary_rank = -float(score) if score is not None else int(position)
            scored_students.append((primary_rank, _student_tie_key(student_id, students_by_id), student_id))

        scored_students.sort()
        normalized[int(project_id)] = [student_id for _, _, student_id in scored_students]
    return normalized


def _rank_maps(preferences: Mapping[int, Sequence[int]]) -> dict[int, dict[int, int]]:
    return {
        int(owner_id): {int(item_id): index for index, item_id in enumerate(items)}
        for owner_id, items in preferences.items()
    }


def _project_tag_names(project) -> set[str]:
    return {_normalize_text(tag.name) for tag in project.tags.all() if tag.name}


def _teacher_gpa_score(student, project) -> float:
    grades = getattr(student, 'grades_json', None) or {}
    if not isinstance(grades, dict) or not grades:
        return 0.0

    subject_to_grade = {
        _normalize_text(subject): max(0.0, min(float(grade), 10.0))
        for subject, grade in grades.items()
        if subject not in (None, '') and grade not in (None, '')
    }
    tag_subjects = getattr(settings, 'PROJECT_TAG_SUBJECTS', {})
    relevant_subjects: set[str] = set()
    for tag in project.tags.all():
        for subject in tag_subjects.get(tag.name, ()):
            relevant_subjects.add(_normalize_text(subject))

    matched = [subject_to_grade[subject] for subject in relevant_subjects if subject in subject_to_grade]
    if not matched:
        return 0.0
    return (sum(matched) / len(matched)) / 10.0


def _teacher_semantic_score(student, project) -> float:
    bio = (getattr(student, 'bio', '') or '').strip()
    description = (getattr(project, 'description', '') or '').strip()
    if not bio or not description:
        return 0.0
    vectors = encode_texts([bio, description])
    if len(vectors) < 2:
        return 0.0
    return max(0.0, float(np.dot(vectors[0], vectors[1])))


def _teacher_tags_score(student, project) -> float:
    student_tags = {_normalize_text(tag.name) for tag in student.interests.all() if tag.name}
    project_tags = _project_tag_names(project)
    if not student_tags or not project_tags:
        return 0.0
    return len(student_tags & project_tags) / len(student_tags | project_tags)


def get_student_score_for_project(student, project) -> float:
    """
    Интерпретируемый скор студента для преподавателя:
    0.4 * GPA_rel + 0.4 * Semantic(student.bio, project.description) + 0.2 * TagsOverlap.
    """
    return (
        TEACHER_GPA_WEIGHT * _teacher_gpa_score(student, project)
        + TEACHER_SEMANTIC_WEIGHT * _teacher_semantic_score(student, project)
        + TEACHER_TAGS_WEIGHT * _teacher_tags_score(student, project)
    )


def pair_score(user, project) -> float:
    return get_student_score_for_project(user, project)


def run_stable_matching(
    students: Iterable,
    projects: Iterable,
    capacities: Mapping[int, int],
    student_prefs: Mapping[int, Sequence],
    project_prefs: Mapping[int, Sequence | Mapping],
) -> dict[int, int]:
    """
    Глобальный many-to-one Gale-Shapley: студенты предлагают проектам.
    Возвращает student_id -> project_id.
    """
    students_by_id = _object_map(students)
    projects_by_id = _object_map(projects)
    normalized_student_prefs = _normalize_preferences(student_prefs)
    normalized_project_prefs = _normalize_project_preferences(project_prefs, students_by_id)
    project_rank = _rank_maps(normalized_project_prefs)

    holding: dict[int, list[int]] = defaultdict(list)
    next_proposal = {student_id: 0 for student_id in normalized_student_prefs}
    queue = deque(
        sorted(
            (student_id for student_id, prefs in normalized_student_prefs.items() if prefs),
            key=lambda student_id: _student_tie_key(student_id, students_by_id),
        )
    )

    while queue:
        student_id = queue.popleft()
        prefs = normalized_student_prefs[student_id]
        proposal_index = next_proposal[student_id]
        if proposal_index >= len(prefs):
            continue

        project_id = prefs[proposal_index]
        if int(capacities.get(project_id, 0)) <= 0:
            next_proposal[student_id] += 1
            queue.append(student_id)
            continue

        holding[project_id].append(student_id)
        holding[project_id].sort(
            key=lambda held_id: (
                project_rank.get(project_id, {}).get(held_id, MISSING_RANK),
                _student_tie_key(held_id, students_by_id),
            )
        )

        capacity = int(capacities.get(project_id, 0))
        rejected = holding[project_id][capacity:]
        holding[project_id] = holding[project_id][:capacity]
        for rejected_id in rejected:
            next_proposal[rejected_id] += 1
            queue.append(rejected_id)

    matching = {}
    for project_id, held_students in holding.items():
        for student_id in held_students:
            matching[student_id] = project_id
    return dict(sorted(matching.items(), key=lambda item: _student_tie_key(item[0], students_by_id)))


def count_blocking_pairs(
    matching: Mapping[int, int],
    capacities: Mapping[int, int],
    student_prefs: Mapping[int, Sequence],
    project_prefs: Mapping[int, Sequence | Mapping],
    students: Optional[Iterable] = None,
) -> int:
    """Считает число blocking pairs для итогового распределения student_id -> project_id."""
    students_by_id = _object_map(students or [])
    normalized_student_prefs = _normalize_preferences(student_prefs)
    normalized_project_prefs = _normalize_project_preferences(project_prefs, students_by_id)
    student_rank = _rank_maps(normalized_student_prefs)
    project_rank = _rank_maps(normalized_project_prefs)

    assigned_by_project: dict[int, list[int]] = defaultdict(list)
    for student_id, project_id in matching.items():
        assigned_by_project[int(project_id)].append(int(student_id))

    blocking_pairs = 0
    for student_id, preferences in normalized_student_prefs.items():
        current_project_id = matching.get(student_id)
        current_rank = student_rank.get(student_id, {}).get(current_project_id, MISSING_RANK)

        for project_id in preferences:
            if student_rank[student_id][project_id] >= current_rank:
                break

            project_order = project_rank.get(project_id, {})
            if student_id not in project_order:
                continue

            assigned_students = assigned_by_project.get(project_id, [])
            if len(assigned_students) < int(capacities.get(project_id, 0)):
                blocking_pairs += 1
                continue

            worst_assigned = max(
                assigned_students,
                key=lambda assigned_id: (
                    project_order.get(assigned_id, MISSING_RANK),
                    _student_tie_key(assigned_id, students_by_id),
                ),
            )
            if project_order[student_id] < project_order.get(worst_assigned, MISSING_RANK):
                blocking_pairs += 1

    return blocking_pairs


def gale_shapley_many_to_one(
    student_prefs: dict[int, list[int]],
    project_capacity: dict[int, int],
    project_student_order: dict[int, list[int]],
) -> dict[int, list[int]]:
    """
    student_prefs[s] — список id проектов по убыванию предпочтения.
    project_capacity[p] — сколько студентов можно назначить на проект p.
    project_student_order[p] — список id студентов от лучшего к худшему для p.
    Возвращает: project_id -> список назначенных student_id.
    """
    matching = run_stable_matching(
        students=student_prefs.keys(),
        projects=project_capacity.keys(),
        capacities=project_capacity,
        student_prefs=student_prefs,
        project_prefs=project_student_order,
    )
    by_project: dict[int, list[int]] = defaultdict(list)
    for student_id, project_id in matching.items():
        by_project[project_id].append(student_id)
    return {project_id: student_ids for project_id, student_ids in by_project.items() if student_ids}


def propose_matching_for_teacher(teacher) -> dict[int, list[int]]:
    projects = list(
        Project.objects.filter(creator=teacher).prefetch_related('tags', 'participants')
    )
    if not projects:
        return {}

    project_ids = {p.pk for p in projects}
    project_capacity = {
        p.pk: max(0, p.max_participants - p.participants.count()) for p in projects
    }

    applications = Application.objects.filter(
        project_id__in=project_ids,
        status=Application.Status.PENDING,
    ).select_related('student', 'project')

    student_to_projects: dict[int, set[int]] = defaultdict(set)
    for app in applications:
        student_to_projects[app.student_id].add(app.project_id)

    student_prefs: dict[int, list[int]] = {}
    for sid, pids in student_to_projects.items():
        user = User.objects.filter(pk=sid).prefetch_related('interests').first()
        if not user:
            continue
        scored = []
        for pid in pids:
            project = next(p for p in projects if p.pk == pid)
            scored.append((pair_score(user, project), pid))
        scored.sort(key=lambda x: (-x[0], _project_tie_key(x[1], {project.pk: project for project in projects})))
        student_prefs[sid] = [
            pid for _, pid in scored if project_capacity.get(pid, 0) > 0
        ]

    project_student_order: dict[int, list[int]] = {}
    for p in projects:
        applicants = [sid for sid in student_to_projects if p.pk in student_to_projects[sid]]
        scored = []
        for sid in applicants:
            user = User.objects.filter(pk=sid).prefetch_related('interests').first()
            if not user:
                continue
            scored.append((pair_score(user, p), sid))
        scored.sort(key=lambda x: (-x[0], _student_tie_key(x[1])))
        project_student_order[p.pk] = [sid for _, sid in scored]

    return gale_shapley_many_to_one(student_prefs, project_capacity, project_student_order)
