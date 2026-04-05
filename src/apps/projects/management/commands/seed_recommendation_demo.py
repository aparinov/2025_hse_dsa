import random
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import Application, Project, Tag

User = get_user_model()

PROGRAMS = [
    ('Прикладная математика и информатика', User.DegreeLevel.BACHELOR),
    ('Программная инженерия', User.DegreeLevel.BACHELOR),
    ('Бизнес-информатика', User.DegreeLevel.BACHELOR),
    ('Анализ данных в экономике', User.DegreeLevel.MASTER),
    ('Системная и программная инженерия', User.DegreeLevel.MASTER),
]

CAMPUSES = ['Москва', 'Санкт-Петербург', 'Нижний Новгород']
STATUS_CHOICES = [
    Application.Status.PENDING,
    Application.Status.APPROVED,
    Application.Status.REJECTED,
]


def _tokenize(value):
    return set(re.findall(r'\w+', (value or '').casefold(), flags=re.UNICODE))


def _build_cover_letter(program, interests):
    interest_names = ', '.join(tag.name for tag in interests[:3])
    return (
        f'Учусь на программе "{program}". Интересуюсь направлениями {interest_names}. '
        'Хочу участвовать в практико-ориентированном проекте, где можно применить знания на реальных данных.'
    )


def _build_grades(all_tags, interests, rng):
    pool = {tag.name: rng.randint(5, 8) for tag in rng.sample(all_tags, k=min(len(all_tags), 4))}
    for tag in interests:
        pool[tag.name] = rng.randint(7, 10)
    return pool


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
    help = 'Создает синтетических студентов, их профили и заявки для демонстрации гибридных рекомендаций.'

    def add_arguments(self, parser):
        parser.add_argument('--students', type=int, default=150)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--max-applications', type=int, default=3)

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

        created_students = 0
        created_applications = 0

        for index in range(1, students_to_create + 1):
            program, degree_level = rng.choice(PROGRAMS)
            interests = rng.sample(tags, k=min(len(tags), rng.randint(2, min(4, len(tags)))))
            cover_letter = _build_cover_letter(program, interests)
            grades_json = _build_grades(tags, interests, rng)

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
            user.bio = 'Синтетический профиль для демонстрации рекомендательной системы.'
            user.cover_letter = cover_letter
            user.grades_json = grades_json
            user.save()
            user.interests.set(interests)

            if was_created:
                created_students += 1

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
                    created_applications += 1
                if application.status == Application.Status.APPROVED:
                    project.participants.add(user)

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: создано {created_students} студентов и {created_applications} заявок.'
            )
        )
