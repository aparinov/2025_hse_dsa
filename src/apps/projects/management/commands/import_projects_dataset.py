import csv
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.projects.management.commands.compute_embeddings import run_compute_embeddings
from apps.projects.models import Project, Tag

User = get_user_model()


def _parse_tags(raw_value):
    if not raw_value:
        return []
    return [
        tag.strip()
        for tag in str(raw_value).replace(';', ',').split(',')
        if tag.strip()
    ]


class Command(BaseCommand):
    help = 'Импортирует проекты из размеченного CSV-файла.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)
        parser.add_argument('--default-password', type=str, default='123')
        parser.add_argument('--application-deadline-days', type=int, default=21)
        parser.add_argument('--end-date-days', type=int, default=120)
        parser.add_argument('--max-participants', type=int, default=3)

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).expanduser().resolve()
        if not csv_path.is_file():
            raise CommandError(f'Файл не найден: {csv_path}')

        created_projects = 0
        updated_projects = 0
        created_teachers = 0
        created_tags = 0

        today = timezone.localdate()
        application_deadline = today + timedelta(days=options['application_deadline_days'])
        end_date = today + timedelta(days=options['end_date_days'])

        with csv_path.open(encoding='utf-8', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            required_columns = {
                'project_id',
                'project_name',
                'professor_email',
                'description',
                'tags',
            }
            if not required_columns.issubset(reader.fieldnames or []):
                missing = ', '.join(sorted(required_columns - set(reader.fieldnames or [])))
                raise CommandError(f'В CSV отсутствуют обязательные колонки: {missing}')

            for row in reader:
                professor_email = row['professor_email'].strip().lower()
                if not professor_email:
                    raise CommandError('У каждого проекта должен быть professor_email')

                username = professor_email.split('@')[0][:150]
                teacher, teacher_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': professor_email,
                        'role': User.Role.TEACHER,
                    },
                )
                if teacher_created:
                    teacher.set_password(options['default_password'])
                    teacher.save()
                    created_teachers += 1

                project, was_created = Project.objects.update_or_create(
                    source_project_id=int(row['project_id']),
                    defaults={
                        'title': row['project_name'].strip(),
                        'description': row['description'].strip(),
                        'creator': teacher,
                        'status': Project.Status.RECRUITMENT,
                        'application_deadline': application_deadline,
                        'end_date': end_date,
                        'max_participants': options['max_participants'],
                    },
                )

                tags = []
                for tag_name in _parse_tags(row['tags']):
                    tag, tag_created = Tag.objects.get_or_create(name=tag_name)
                    tags.append(tag)
                    if tag_created:
                        created_tags += 1
                project.tags.set(tags)

                if was_created:
                    created_projects += 1
                else:
                    updated_projects += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Импорт завершен: '
                f'{created_projects} создано, {updated_projects} обновлено, '
                f'{created_teachers} преподавателей создано, {created_tags} новых тегов.'
            )
        )
        run_compute_embeddings(stdout=self.stdout)
