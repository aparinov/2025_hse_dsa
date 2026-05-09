"""Маппинг предметов из grades_json на теги через эмбеддинги."""
from collections import defaultdict

import numpy as np

from apps.projects.embeddings import encode_text, encode_texts, to_list
from apps.projects.models import Tag

SUBJECT_TAG_COSINE_THRESHOLD = 0.3


def ensure_tag_embeddings(tags: list[Tag]) -> np.ndarray:
    """Гарантирует embedding у каждого тега; возвращает матрицу (n_tags, dim)."""
    if not tags:
        return np.zeros((0, 384), dtype=np.float64)
    to_encode = []
    indices = []
    for i, tag in enumerate(tags):
        if not tag.embedding:
            to_encode.append(tag.name)
            indices.append(i)
    if to_encode:
        matrix = encode_texts(to_encode)
        for pos, idx in enumerate(indices):
            vec = to_list(matrix[pos])
            Tag.objects.filter(pk=tags[idx].pk).update(embedding=vec)
            tags[idx].embedding = vec
    rows = []
    for tag in tags:
        rows.append(np.asarray(tag.embedding, dtype=np.float64))
    return np.stack(rows, axis=0)


def rebuild_grade_profile(user) -> dict[str, float]:
    """
    Заполняет user.grade_profile: имя тега -> средняя оценка (0..10).
    Обновляет только поле grade_profile в БД.
    """
    from apps.users.models import User

    if not getattr(user, 'is_student', False):
        User.objects.filter(pk=user.pk).update(grade_profile={})
        return {}

    grades = getattr(user, 'grades_json', None) or {}
    if not isinstance(grades, dict) or not grades:
        User.objects.filter(pk=user.pk).update(grade_profile={})
        return {}

    tags = list(Tag.objects.all().order_by('pk'))
    if not tags:
        User.objects.filter(pk=user.pk).update(grade_profile={})
        return {}

    tag_matrix = ensure_tag_embeddings(tags)
    buckets: dict[int, list[float]] = defaultdict(list)

    for subject, raw_grade in grades.items():
        if subject is None or raw_grade in (None, ''):
            continue
        subject_text = str(subject).strip()
        if not subject_text:
            continue
        try:
            grade_val = float(raw_grade)
        except (TypeError, ValueError):
            continue
        grade_val = max(0.0, min(grade_val, 10.0))
        subj_vec = encode_text(subject_text)
        sims = tag_matrix @ subj_vec
        best_idx = int(np.argmax(sims))
        if sims[best_idx] < SUBJECT_TAG_COSINE_THRESHOLD:
            continue
        buckets[best_idx].append(grade_val)

    profile: dict[str, float] = {}
    for idx, grades_list in buckets.items():
        profile[tags[idx].name] = sum(grades_list) / len(grades_list)

    User.objects.filter(pk=user.pk).update(grade_profile=profile)
    return profile
