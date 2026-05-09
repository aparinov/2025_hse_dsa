"""
Планы синтетических студентов: согласованные кластеры тегов + заготовка под LLM-батч.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from django.contrib.auth import get_user_model

from apps.projects.models import Tag

User = get_user_model()

PROGRAMS = [
    ('Прикладная математика и информатика', User.DegreeLevel.BACHELOR),
    ('Программная инженерия', User.DegreeLevel.BACHELOR),
    ('Бизнес-информатика', User.DegreeLevel.BACHELOR),
    ('Анализ данных в экономике', User.DegreeLevel.MASTER),
    ('Системная и программная инженерия', User.DegreeLevel.MASTER),
]

CAMPUSES = ['Москва', 'Санкт-Петербург', 'Нижний Новгород']

# Подмножества общего словаря тегов; пересечение с реальными Tag в БД берётся при выборе.
TAG_CLUSTERS: tuple[frozenset[str], ...] = (
    frozenset({
        'Machine Learning',
        'Data Science',
        'Analytics',
        'Recommendation Systems',
        'NLP',
        'Computer Vision',
    }),
    frozenset({'Backend', 'Frontend', 'Web Development', 'DevOps'}),
    frozenset({'Finance', 'Economics', 'Analytics', 'Business Analysis'}),
    frozenset({'Marketing', 'Strategy', 'Product Management', 'Business Analysis'}),
    frozenset({'Research', 'Education', 'Legal Tech', 'Design'}),
)

DEGREE_LABEL_RU = {
    User.DegreeLevel.BACHELOR: 'бакалавриат',
    User.DegreeLevel.MASTER: 'магистратура',
}


def pick_coherent_interests(tags: list[Tag], rng: random.Random) -> list[Tag]:
    """2–4 тега из одного кластера, присутствующего в БД (пересечение имён)."""
    by_name = {t.name: t for t in tags}
    viable: list[list[Tag]] = []
    for cluster in TAG_CLUSTERS:
        present = [by_name[n] for n in cluster if n in by_name]
        if len(present) >= 2:
            viable.append(present)
    if not viable:
        k = min(len(tags), rng.randint(2, min(4, max(len(tags), 2))))
        return rng.sample(tags, k=k) if len(tags) >= 2 else list(tags)

    pool = rng.choice(viable)
    upper = min(4, len(pool))
    lower = min(2, upper)
    k = rng.randint(lower, upper)
    return rng.sample(pool, k=k)


def study_year_for(degree_level: str, rng: random.Random) -> int:
    if degree_level == User.DegreeLevel.BACHELOR:
        return rng.randint(1, 4)
    return rng.randint(1, 2)


def plan_rows(tags: list[Tag], rng: random.Random, count: int) -> list[dict]:
    """План для одного LLM-батча: демография + согласованные теги (имена строк)."""
    rows: list[dict] = []
    for index in range(1, count + 1):
        program, degree_level = rng.choice(PROGRAMS)
        interests = pick_coherent_interests(tags, rng)
        rows.append(
            {
                'index': index,
                'program': program,
                'degree_level': degree_level,
                'degree_label': DEGREE_LABEL_RU.get(degree_level, degree_level),
                'campus': rng.choice(CAMPUSES),
                'study_year': study_year_for(degree_level, rng),
                'tags': [t.name for t in interests],
            }
        )
    return rows


def format_llm_prompt(rows: list[dict]) -> str:
    """Один большой текст для вставки в чат с LLM (без API)."""
    lines = []
    for r in rows:
        tag_line = ', '.join(r['tags'])
        lines.append(
            f"- index={r['index']}, программа={r['program']}, кампус={r['campus']}, "
            f"курс={r['study_year']}, уровень={r['degree_label']}, теги: {tag_line}"
        )
    block = '\n'.join(lines)
    n = len(rows)
    return f"""Ты генерируешь правдоподобные профили студентов ВШЭ для демо рекомендательной системы проектов.

Правила:
- Пиши на русском.
- Поля bio и cover_letter должны быть согласованы с указанными тегами (интересы в тематике DS/IT/бизнес и т.д.).
- bio: 2–4 предложения о себе, опыте и целях.
- cover_letter: 3–6 предложений, почему интересны проектные работы и как совпадают с тегами.
- Не выдумывай конкретные имена компаний/лабораторий, если не уверен; можно обобщать («крупный маркетплейс», «IT-компания»).

Верни строго один JSON-массив из ровно {n} объектов (без markdown, без комментариев вне JSON):
[
  {{"index": <int>, "bio": "<строка>", "cover_letter": "<строка>"}},
  ...
]

Индексы index должны совпасть с перечисленными ниже.

Студенты:
{block}
"""


def load_llm_profiles(path: Path | str) -> dict[int, dict]:
    """Читает JSON: массив объектов с ключом index или обёртку {{"students": [...]}}."""
    path = Path(path)
    with path.open(encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and 'students' in data:
        data = data['students']
    if not isinstance(data, list):
        raise ValueError('Ожидался JSON-массив профилей или объект с ключом "students"')
    out: dict[int, dict] = {}
    for item in data:
        idx = int(item['index'])
        out[idx] = item
    return out


def parse_llm_json_array(text: str) -> list[dict]:
    """Снимает при необходимости обёртку ```json ... ``` и парсит массив."""
    s = text.strip()
    if s.startswith('```'):
        lines = s.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        s = '\n'.join(lines)
    data = json.loads(s)
    if not isinstance(data, list):
        raise ValueError('Ответ LLM должен быть JSON-массивом')
    return data
