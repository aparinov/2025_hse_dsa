import json
from pathlib import Path

from django.conf import settings
from django.db.models import Case, Count, IntegerField, Q, When

from .models import Project

_synthetic_json_cache = None
_synthetic_json_mtime = None


def _load_synthetic_ranking():
    global _synthetic_json_cache, _synthetic_json_mtime
    path = Path(settings.SYNTHETIC_RECOMMENDATIONS_FILE)
    if not path.is_file():
        _synthetic_json_cache = None
        _synthetic_json_mtime = None
        return None
    mtime = path.stat().st_mtime
    if _synthetic_json_cache is not None and _synthetic_json_mtime == mtime:
        return _synthetic_json_cache
    with path.open(encoding='utf-8') as f:
        _synthetic_json_cache = json.load(f)
    _synthetic_json_mtime = mtime
    return _synthetic_json_cache


def _eligible_recommendation_projects(user):
    return Project.objects.filter(status=Project.Status.RECRUITMENT).exclude(
        Q(creator=user) | Q(participants=user)
    )


def _projects_from_synthetic_order(user, ordered_pks):
    allowed = set(_eligible_recommendation_projects(user).values_list('pk', flat=True))
    filtered = [pk for pk in ordered_pks if pk in allowed]
    if not filtered:
        return None
    order = Case(
        *[When(pk=pk, then=pos) for pos, pk in enumerate(filtered)],
        output_field=IntegerField(),
    )
    return (
        Project.objects.filter(pk__in=filtered)
        .order_by(order)
        .distinct()
    )


def get_recommended_projects(user):
    """
    Рекомендации проектов для студента.

    Если существует файл synthetic_recommendations.json (см. generate_synthetic_recommendations),
    порядок проектов берётся оттуда (после фильтрации по статусу/участию).
    Иначе — по пересечению тегов интересов и тегов проекта.
    """
    if not user.is_authenticated or not getattr(user, 'is_student', False):
        return Project.objects.none()

    data = _load_synthetic_ranking()
    if isinstance(data, dict) and user.username in data:
        ordered = data[user.username]
        if isinstance(ordered, list) and ordered:
            qs = _projects_from_synthetic_order(user, ordered)
            if qs is not None:
                return qs

    user_interests = user.interests.all()
    if not user_interests.exists():
        return Project.objects.none()

    return (
        Project.objects.filter(
            tags__in=user_interests,
            status=Project.Status.RECRUITMENT,
        )
        .exclude(Q(creator=user) | Q(participants=user))
        .annotate(matching_tags=Count('tags', filter=Q(tags__in=user_interests)))
        .order_by('-matching_tags', '-created_at')
        .distinct()
    )
