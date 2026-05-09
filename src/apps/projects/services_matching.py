"""
Стабильное распределение заявок (Гейл–Шепли) по проектам преподавателя.
Использует скор пары студент–проект (теги + семантика + оценки, без коллаборативки).
"""
from collections import defaultdict

from django.contrib.auth import get_user_model

from apps.projects.models import Application, Project

from .services import GRADES_WEIGHT, SEMANTIC_WEIGHT, TAG_WEIGHT, _grades_scores, _semantic_scores, _tag_scores

User = get_user_model()


def pair_score(user, project) -> float:
    projects = [project]
    tag = _tag_scores(user, projects).get(project.pk, 0.0)
    sem = _semantic_scores(user, projects).get(project.pk, 0.0)
    gr = _grades_scores(user, projects).get(project.pk, 0.0)
    return TAG_WEIGHT * tag + SEMANTIC_WEIGHT * sem + GRADES_WEIGHT * gr


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
    from collections import deque

    rank_on_project = {
        pid: {sid: i for i, sid in enumerate(order)}
        for pid, order in project_student_order.items()
    }

    holding: dict[int, list[int]] = defaultdict(list)
    next_proposal = {s: 0 for s in student_prefs}
    queue = deque(s for s in student_prefs if student_prefs[s])

    while queue:
        s = queue.popleft()
        prefs = student_prefs[s]
        i = next_proposal[s]
        if i >= len(prefs):
            continue
        p = prefs[i]
        cap = project_capacity.get(p, 0)
        if cap <= 0:
            next_proposal[s] += 1
            queue.append(s)
            continue

        holding[p].append(s)
        holding[p].sort(key=lambda sid: rank_on_project.get(p, {}).get(sid, 10**9))
        if len(holding[p]) > cap:
            worst = holding[p].pop()
            next_proposal[worst] += 1
            queue.append(worst)

    return {pid: list(students) for pid, students in holding.items() if students}


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
        scored.sort(key=lambda x: -x[0])
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
        scored.sort(key=lambda x: -x[0])
        project_student_order[p.pk] = [sid for _, sid in scored]

    return gale_shapley_many_to_one(student_prefs, project_capacity, project_student_order)
