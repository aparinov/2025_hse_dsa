import random
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import Application, Project, Tag
from apps.projects.synthetic_student_profiles import (
    CAMPUSES,
    PROGRAMS,
    load_llm_profiles,
    pick_coherent_interests,
)

User = get_user_model()

STATUS_CHOICES = [
    Application.Status.PENDING,
    Application.Status.APPROVED,
    Application.Status.REJECTED,
]


def _tokenize(value):
    return set(re.findall(r'\w+', (value or '').casefold(), flags=re.UNICODE))


def _build_cover_letter(program, interests):
    interest_names = ', '.join(tag.name for tag in interests[:4])
    return (
        f'Учусь на программе "{program}". Интересуюсь направлениями {interest_names}. '
        'Хочу участвовать в практико-ориентированном проекте, где можно применить знания на реальных данных.'
    )


def _build_grades(interests, rng):
    """Оценки по тем же осям, что и интересы (имена тегов), чтобы grade_profile был согласован."""
    base = {tag.name: rng.randint(7, 10) for tag in interests}
    return base


def _project_score(project, interests, grades_json, cover_letter_tokens):
    project_tag_names = {tag.name for tag in project.tags.all()}
    project_tokens = _tokenize(' '.join([project.title, project.description, *project_tag_names]))

    overlap_tags = len(project_tag_names & {tag.name for tag in interests})
    text_overlap = len(project_tokens & cover_letter_tokens)

    grades_score = 0
    if grades_json:
        matched = [grade for subject, grade in grades_json.items() if subject in project_tag_names]
        if matched:
            grades_score = sum(matched) / len(matched)

    return 1 + overlap_tags * 4 + text_overlap * 0.2 + grades_score * 0.3


class Command(BaseCommand):
    help = (
        'Создает синтетических студентов с согласованными тегами (кластеры). '
        'Опционально подмешивает bio/cover_letter из JSON после LLM-батча (--profiles-json).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--students', type=int, default=150)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--max-applications', type=int, default=3)
        default_profiles = settings.BASE_DIR / 'data' / 'synthetic_student_profiles.json'
        parser.add_argument(
            '--profiles-json',
            type=str,
            default=str(default_profiles) if default_profiles.is_file() else '',
            help='Путь к JSON-массиву от LLM: [{"index": 1, "bio": "...", "cover_letter": "..."}, ...]',
        )

    def handle(self, *args, **options):
        tags = list(Tag.objects.all())
        projects = list(
            Project.objects.filter(status=Project.Status.RECRUITMENT)
            .prefetch_related('tags')
        )
        if not tags:
            raise CommandError('Сначала создайте теги и проекты.')
        if not projects:
            raise CommandError('Сначала загрузите хотя бы один проект со статусом RECRUITMENT.')

        rng = random.Random(options['seed'])
        students_to_create = options['students']
        max_applications = max(1, options['max_applications'])

        profiles_path = (options['profiles_json'] or '').strip()
        llm_profiles: dict[int, dict] = {}
        if profiles_path:
            path = Path(profiles_path)
            if not path.is_file():
                raise CommandError(f'Файл профилей не найден: {path}')
            llm_profiles = load_llm_profiles(path)

        created_accounts = 0
        new_applications = 0

        for index in range(1, students_to_create + 1):
            program, degree_level = rng.choice(PROGRAMS)
            interests = pick_coherent_interests(tags, rng)
            llm = llm_profiles.get(index)

            cover_letter = _build_cover_letter(program, interests)
            grades_json = _build_grades(interests, rng)
            bio = 'Синтетический профиль для демонстрации рекомендательной системы.'

            if llm:
                bio = (llm.get('bio') or bio).strip() or bio
                cover_letter = (llm.get('cover_letter') or llm.get('cover') or cover_letter).strip() or cover_letter
                if isinstance(llm.get('grades'), dict):
                    grades_json = llm['grades']
                elif isinstance(llm.get('grades_json'), dict):
                    grades_json = llm['grades_json']

            user, was_created = User.objects.get_or_create(
                username=f'synthetic_student_{index}',
                defaults={
                    'email': f'synthetic_student_{index}@example.com',
                    'first_name': 'Synthetic',
                    'last_name': f'Student {index}',
                    'role': User.Role.STUDENT,
                },
            )
            user.set_password('123')
            user.role = User.Role.STUDENT
            user.campus = rng.choice(CAMPUSES)
            user.program = program
            user.study_year = rng.randint(1, 4 if degree_level == User.DegreeLevel.BACHELOR else 2)
            user.degree_level = degree_level
            user.bio = bio
            user.cover_letter = cover_letter
            user.grades_json = grades_json
            user.save()
            user.interests.set(interests)

            if was_created:
                created_accounts += 1

            cover_letter_tokens = _tokenize(cover_letter)
            weighted_projects = [
                (project, _project_score(project, interests, grades_json, cover_letter_tokens))
                for project in projects
                if project.creator_id != user.id
            ]
            if not weighted_projects:
                continue

            weighted_projects.sort(key=lambda item: item[1], reverse=True)
            chosen_projects = weighted_projects[:max_applications * 3]
            sample_size = min(len(chosen_projects), rng.randint(1, max_applications))
            selected = rng.sample(chosen_projects, k=sample_size)

            for project, _score in selected:
                application, app_created = Application.objects.get_or_create(
                    project=project,
                    student=user,
                    defaults={'status': rng.choices(STATUS_CHOICES, weights=[3, 4, 1], k=1)[0]},
                )
                if app_created:
                    new_applications += 1
                if application.status == Application.Status.APPROVED:
                    project.participants.add(user)

        updated_existing = students_to_create - created_accounts
        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: обработано профилей {students_to_create} '
                f'(новых учёток: {created_accounts}, обновлено существующих: {updated_existing}). '
                f'Новых заявок в БД: {new_applications}.'
            )
        )
        call_command('compute_embeddings')
