import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.projects.models import Tag, Project, Application

User = get_user_model()

TAGS = ['Python', 'Machine Learning', 'Data Science', 'Web Development', 'UX/UI', 'DevOps', 'GameDev']
STUDENT_NAMES = [('Иван', 'Петров'), ('Мария', 'Сидорова'), ('Алексей', 'Иванов'), ('Елена', 'Кузнецова')]
TEACHER_NAME = ('Аркадий', 'Паровозов')

class Command(BaseCommand):
    help = 'Fills the database with pseudo-data for testing.'

    def handle(self, *args, **options):
        self.stdout.write("Deleting old data...")
        Tag.objects.all().delete()
        Project.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()

        self.stdout.write("Creating new data...")

        # Создание тегов
        tags = [Tag.objects.create(name=name) for name in TAGS]

        # Создание преподавателя
        teacher, _ = User.objects.get_or_create(
            username='teacher1',
            defaults={
                'first_name': TEACHER_NAME[0],
                'last_name': TEACHER_NAME[1],
                'email': 'teacher@test.com',
                'role': User.Role.TEACHER,
            }
        )
        teacher.set_password('123')
        teacher.save()

        # Создание студентов
        students = []
        for i, (first_name, last_name) in enumerate(STUDENT_NAMES):
            student, _ = User.objects.get_or_create(
                username=f'student{i+1}',
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': f'student{i+1}@test.com',
                    'role': User.Role.STUDENT,
                }
            )
            student.set_password('123')
            student.interests.set(random.sample(tags, k=3))
            student.save()
            students.append(student)

        # Создание проектов
        for i in range(5):
            project = Project.objects.create(
                title=f'Исследовательский проект №{i+1}',
                description=f'Подробное описание проекта {i+1}. Цель - изучить...',
                creator=teacher,
                max_participants=random.randint(2, 5),
                application_deadline='2024-12-31',
                end_date='2025-05-31',
            )
            project.tags.set(random.sample(tags, k=2))

        self.stdout.write(self.style.SUCCESS('Successfully seeded the database.'))
