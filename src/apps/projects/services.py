import math
import re
from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Case, Count, IntegerField, Q, When

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


def _tokenize(value):
    return re.findall(r'\w+', _normalize_text(value), flags=re.UNICODE)


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


def _build_tfidf_vectors(texts):
    tokenized = [_tokenize(text) for text in texts]
    if not any(tokenized):
        return [Counter() for _ in texts]

    total_docs = len(tokenized)
    doc_frequency = Counter()
    for tokens in tokenized:
        for token in set(tokens):
            doc_frequency[token] += 1

    vectors = []
    for tokens in tokenized:
        counts = Counter(tokens)
        size = sum(counts.values()) or 1
        vector = Counter()
        for token, count in counts.items():
            idf = math.log((1 + total_docs) / (1 + doc_frequency[token])) + 1
            vector[token] = (count / size) * idf
        vectors.append(vector)
    return vectors


def _cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


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
    source_text = _user_text(user)
    if not source_text:
        return {}

    texts = [source_text, *(_project_text(project) for project in projects)]
    vectors = _build_tfidf_vectors(texts)
    user_vector = vectors[0]

    scores = {}
    for project, vector in zip(projects, vectors[1:]):
        similarity = _cosine_similarity(user_vector, vector)
        if similarity > 0:
            scores[project.pk] = similarity
    return _normalize_scores(scores)


def _grades_scores(user, projects):
    grades = getattr(user, 'grades_json', {}) or {}
    if not isinstance(grades, dict):
        return {}

    normalized_grades = {}
    for subject, grade in grades.items():
        if subject is None or grade in (None, ''):
            continue
        normalized_subject = _normalize_text(subject)
        if not normalized_subject:
            continue
        normalized_grades[normalized_subject] = max(0.0, min(float(grade), 10.0)) / 10.0

    if not normalized_grades:
        return {}

    scores = {}
    for project in projects:
        project_terms = set(_tokenize(_project_text(project)))
        if not project_terms:
            continue
        weighted_sum = 0.0
        matched_weight = 0.0
        for subject, grade in normalized_grades.items():
            subject_terms = set(_tokenize(subject))
            overlap = project_terms & subject_terms
            if not overlap:
                continue
            weight = len(overlap) / len(subject_terms)
            weighted_sum += grade * weight
            matched_weight += weight
        if matched_weight:
            scores[project.pk] = weighted_sum / matched_weight
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
    3. Текстовая близость профиля студента и описания проекта.
    4. Сопоставление оценок студента с темами проекта.
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
