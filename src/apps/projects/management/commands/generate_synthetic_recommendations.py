import json
import random
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.projects.models import Project

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Строит простой синтетический ранжированный список id проектов на каждого студента '
        '(детерминированный shuffle по username) и сохраняет в SYNTHETIC_RECOMMENDATIONS_FILE.'
    )

    def handle(self, *args, **options):
        path = Path(settings.SYNTHETIC_RECOMMENDATIONS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {}
        students = User.objects.filter(role=User.Role.STUDENT)
        for user in students:
            pks = list(
                Project.objects.filter(status=Project.Status.RECRUITMENT)
                .exclude(creator=user)
                .exclude(participants=user)
                .values_list('pk', flat=True)
            )
            rng = random.Random(user.username)
            rng.shuffle(pks)
            payload[user.username] = pks

        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Записано {path} ({len(payload)} студентов).'))
