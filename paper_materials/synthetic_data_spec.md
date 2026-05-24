# Synthetic Data Specification

Синтетический контур предназначен для воспроизводимого сравнения внутренних сценариев статьи, а не для имитации реальной истории заявок.

- Когорта: 150 студентов `synthetic_student_1..150` (после `seed_recommendation_demo` + `synthetic_student_profiles.json`).
- Проекты: семпл 100 из всех `RECRUITMENT` (seed=42), не полный каталог 200.
- Профили: `bio`, `cover_letter`, `program`, `interests`, `grades_json`.
- Ground truth: внешний LLM-пайплайн в `experiments.ipynb` используется как ручной аудит; по умолчанию считается контролируемый hidden relevance без popularity и capacity: `0.40 * TagsOverlap + 0.45 * Semantic + 0.15 * GPA_rel`.
- Long-tail спрос: `20%` проектов получают `80%` органического спроса в Base-сценарии; оставшиеся `80%` проектов делят `20%` спроса.
- Top-K заявок: `K = 5`; для RecSys-метрик дополнительно считаются горизонты `K = 1, 5, 10, 20`.
- Hybrid: GS-first reranking — проект из Stable Matching ставится первым в персональной выдаче, затем идут остальные RecSys-рекомендации в исходном порядке.
- RecSys + Prof. Rank: заявки остаются из исходного RecSys top-5, но эффективная выдача для метрик дополнительно учитывает fit со стороны преподавателя.
- RecSysScore: `0.45 * TagsOverlap + 0.25 * PopularityPrior + 0.20 * Semantic + 0.10 * GPA_rel`.
- ProfScore: `0.40 * GPA_rel + 0.40 * Semantic(student.bio, project.description) + 0.20 * TagsOverlap`.
- GPA_rel: средняя оценка только по предметам из `PROJECT_TAG_SUBJECTS` для тегов проекта, нормированная на шкалу `0..1`.
- Семантический шум: эмбеддинги `paraphrase-multilingual-MiniLM-L12-v2`; при недоступности модели используется лексическая cosine-близость как воспроизводимый fallback.
- Capacity: берется из `Project.max_participants`, минимум `1` для эксперимента.
- Tie-breaking: при равных рангах выигрывает студент с более ранней регистрацией, затем меньший `id`.
- Blocking pairs: считаются относительно фактических списков заявок `top-5`, которые участвовали в назначении; для Stable Matching это тот же набор предпочтений, на котором запускался Gale-Shapley.
- Гистограммы: все сценарии рисуются в одном порядке проектов — по убыванию спроса в `Base`, чтобы сравнивать одни и те же проекты между сценариями.
