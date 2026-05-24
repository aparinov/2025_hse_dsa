# Synthetic Data Specification

Синтетический контур предназначен для воспроизводимого сравнения внутренних сценариев статьи, а не для имитации реальной истории заявок.

- Когорта: 150 студентов `synthetic_student_1..150` (после `seed_recommendation_demo` + `synthetic_student_profiles.json`).
- Проекты: семпл 100 из всех `RECRUITMENT` (seed=42), не полный каталог 200.
- Профили: `bio`, `cover_letter`, `program`, `interests`, `grades_json`.
- Ground truth: внешний LLM-пайплайн в `experiments.ipynb`; если JSON-ответ не вставлен, используется proxy GT как максимум скрытой смеси `0.70 * RecSysScore + 0.30 * ProfScore`.
- Long-tail спрос: `20%` проектов получают `80%` органического спроса в Base-сценарии; оставшиеся `80%` проектов делят `20%` спроса.
- Top-K заявок: `K = 5`.
- Hybrid: `0.65 * RecSysScore + 0.35 * MatchingScore`.
- RecSysScore: `0.45 * TagsOverlap + 0.25 * PopularityPrior + 0.20 * Semantic + 0.10 * GPA_rel`.
- ProfScore: `0.40 * GPA_rel + 0.40 * Semantic(student.bio, project.description) + 0.20 * TagsOverlap`.
- GPA_rel: средняя оценка только по предметам из `PROJECT_TAG_SUBJECTS` для тегов проекта, нормированная на шкалу `0..1`.
- Семантический шум: эмбеддинги `paraphrase-multilingual-MiniLM-L12-v2`; при недоступности модели используется лексическая cosine-близость как воспроизводимый fallback.
- Capacity: берется из `Project.max_participants`, минимум `1` для эксперимента.
- Tie-breaking: при равных рангах выигрывает студент с более ранней регистрацией, затем меньший `id`.
