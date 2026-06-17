import math
import re
from collections import Counter, defaultdict

import numpy as np
from django.contrib.auth import get_user_model
from django.db.models import Case, Count, IntegerField, Q, When

from .embeddings import encode_text, to_list
from .models import Application, Project

User = get_user_model()

TAG_WEIGHT = 0.45
COLLAB_WEIGHT = 0.25
SEMANTIC_WEIGHT = 0.20
GRADES_WEIGHT = 0.10

APPLICATION_STATUS_WEIGHT = {
    Application.Status.APPROVED: 1.0,
    Application.Status.PENDING: 0.7,
    Application.Status.REJECTED: 0.2,
}


def _eligible_recommendation_projects(user):
    return (
        Project.objects.filter(status=Project.Status.RECRUITMENT)
        .exclude(Q(creator=user) | Q(participants=user))
        .annotate(participant_count=Count('participants', distinct=True))
    )


def _normalize_text(value):
    return (value or '').strip().casefold()


def _tokens(value):
    return Counter(re.findall(r'[\wа-яА-ЯёЁ]+', _normalize_text(value)))


def _cosine_counts(left, right):
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm)


def _project_text(project):
    tags = ' '.join(tag.name for tag in project.tags.all())
    return ' '.join(part for part in (project.title, project.description, tags) if part)


def _user_text(user):
    return ' '.join(
        part
        for part in (
            getattr(user, 'cover_letter', ''),
            getattr(user, 'bio', ''),
            getattr(user, 'program', ''),
        )
        if part
    )


def _normalized_interest_names(user):
    return {
        _normalize_text(name)
        for name in user.interests.values_list('name', flat=True)
        if name
    }


def _normalize_scores(raw_scores):
    positive_scores = [score for score in raw_scores.values() if score > 0]
    if not positive_scores:
        return {}
    max_score = max(positive_scores)
    return {
        key: score / max_score
        for key, score in raw_scores.items()
        if score > 0
    }


def _ensure_user_embedding(user):
    text = _user_text(user)
    if not text.strip():
        return None
    stored = getattr(user, 'profile_embedding', None)
    if stored:
        return np.asarray(stored, dtype=np.float64)
    vector = encode_text(text)
    User.objects.filter(pk=user.pk).update(profile_embedding=to_list(vector))
    return vector


def _ensure_project_embedding(project):
    stored = getattr(project, 'embedding', None)
    if stored:
        return np.asarray(stored, dtype=np.float64)
    text = _project_text(project)
    if not text.strip():
        return None
    vector = encode_text(text)
    Project.objects.filter(pk=project.pk).update(embedding=to_list(vector))
    return vector


def _tag_scores(user, projects):
    user_tags = _normalized_interest_names(user)
    if not user_tags:
        return {}

    scores = {}
    for project in projects:
        project_tags = {_normalize_text(tag.name) for tag in project.tags.all() if tag.name}
        if not project_tags:
            continue
        intersection = user_tags & project_tags
        if intersection:
            union = user_tags | project_tags
            scores[project.pk] = len(intersection) / len(union)
    return scores


def _collaborative_scores(user, projects):
    user_tags = _normalized_interest_names(user)
    if not user_tags:
        return {}

    peers = (
        User.objects.filter(role=User.Role.STUDENT, interests__in=user.interests.all())
        .exclude(pk=user.pk)
        .prefetch_related('interests')
        .distinct()
    )
    if not peers:
        return {}

    peer_weights = {}
    for peer in peers:
        peer_tags = {
            _normalize_text(tag.name)
            for tag in peer.interests.all()
            if tag.name
        }
        overlap = user_tags & peer_tags
        if overlap:
            peer_weights[peer.pk] = len(overlap) / len(user_tags)

    if not peer_weights:
        return {}

    project_ids = [project.pk for project in projects]
    raw_scores = defaultdict(float)
    applications = Application.objects.filter(
        student_id__in=peer_weights,
        project_id__in=project_ids,
    ).select_related('student')

    for application in applications:
        raw_scores[application.project_id] += (
            peer_weights[application.student_id]
            * APPLICATION_STATUS_WEIGHT.get(application.status, 0.0)
        )

    return _normalize_scores(raw_scores)


def _semantic_scores(user, projects):
    try:
        user_emb = _ensure_user_embedding(user)
    except Exception:
        user_emb = None

    if user_emb is None:
        user_tokens = _tokens(_user_text(user))
        return _normalize_scores(
            {
                project.pk: _cosine_counts(user_tokens, _tokens(_project_text(project)))
                for project in projects
            }
        )

    scores = {}
    for project in projects:
        try:
            proj_emb = _ensure_project_embedding(project)
        except Exception:
            proj_emb = None
        if proj_emb is None:
            continue
        similarity = float(np.dot(user_emb, proj_emb))
        if similarity > 0:
            scores[project.pk] = similarity
    return _normalize_scores(scores)


def _grades_scores(user, projects):
    profile = getattr(user, 'grade_profile', None) or {}
    if not isinstance(profile, dict) or not profile:
        return {}

    scores = {}
    for project in projects:
        tag_names = [tag.name for tag in project.tags.all()]
        matched = [float(profile[name]) for name in tag_names if name in profile]
        if matched:
            scores[project.pk] = (sum(matched) / len(matched)) / 10.0
    return _normalize_scores(scores)


def _participant_count(project):
    return getattr(project, 'participant_count', project.participants.count())


def _effective_rank_score(project, weighted_scores):
    base = weighted_scores.get(project.pk, 0.0)
    if _participant_count(project) >= project.max_participants:
        return base * 0.5
    return base


def _rank_projects(projects, weighted_scores):
    scored_ids = [
        project.pk
        for project in sorted(
            projects,
            key=lambda p: (
                -_effective_rank_score(p, weighted_scores),
                -p.created_at.timestamp(),
            ),
        )
        if weighted_scores.get(project.pk, 0.0) > 0
    ]
    if not scored_ids:
        return Project.objects.none()

    order = Case(
        *[When(pk=pk, then=position) for position, pk in enumerate(scored_ids)],
        output_field=IntegerField(),
    )
    return Project.objects.filter(pk__in=scored_ids).order_by(order)


def get_recommended_projects(user):
    """
    Возвращает гибридные рекомендации для студента.

    Сигналы:
    1. Совпадение тегов пользователя и проекта.
    2. Top-pop проекты среди студентов с похожими тегами.
    3. Текстовая близость профиля студента и описания проекта (эмбеддинги).
    4. Сопоставление оценок студента с тегами проекта (grade_profile).
    """
    if not user.is_authenticated or not getattr(user, 'is_student', False):
        return Project.objects.none()

    projects = list(_eligible_recommendation_projects(user).prefetch_related('tags'))
    if not projects:
        return Project.objects.none()

    tag_scores = _tag_scores(user, projects)
    collab_scores = _collaborative_scores(user, projects)
    semantic_scores = _semantic_scores(user, projects)
    grades_scores = _grades_scores(user, projects)

    weighted_scores = defaultdict(float)
    for project in projects:
        weighted_scores[project.pk] += TAG_WEIGHT * tag_scores.get(project.pk, 0.0)
        weighted_scores[project.pk] += COLLAB_WEIGHT * collab_scores.get(project.pk, 0.0)
        weighted_scores[project.pk] += SEMANTIC_WEIGHT * semantic_scores.get(project.pk, 0.0)
        weighted_scores[project.pk] += GRADES_WEIGHT * grades_scores.get(project.pk, 0.0)

    return _rank_projects(projects, weighted_scores)
