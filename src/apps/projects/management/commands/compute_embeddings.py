from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.projects.embeddings import encode_texts, to_list
from apps.projects.models import Project, Tag

User = get_user_model()


def _project_text(project):
    tags = ' '.join(tag.name for tag in project.tags.all())
    parts = [project.title, project.description, tags]
    return ' '.join(p for p in parts if p)


def _user_text(user):
    return ' '.join(
        part
        for part in (
            getattr(user, 'cover_letter', ''),
            getattr(user, 'bio', ''),
            getattr(user, 'program', ''),
        )
        if part
    )


def run_compute_embeddings(stdout=None):
    try:
        encode_texts(['dependency check'])
    except Exception as exc:
        if stdout:
            stdout.write(f'Эмбеддинги пропущены: {exc}')
        return

    tags = list(Tag.objects.all().order_by('pk'))
    if tags:
        vectors = encode_texts([t.name for t in tags])
        for tag, row in zip(tags, vectors):
            Tag.objects.filter(pk=tag.pk).update(embedding=to_list(row))

    projects = list(Project.objects.prefetch_related('tags').order_by('pk'))
    if projects:
        texts = [_project_text(p) for p in projects]
        vectors = encode_texts(texts)
        for project, row in zip(projects, vectors):
            Project.objects.filter(pk=project.pk).update(embedding=to_list(row))

    students = User.objects.filter(role=User.Role.STUDENT).order_by('pk')
    for user in students.iterator():
        text = _user_text(user)
        if not text.strip():
            User.objects.filter(pk=user.pk).update(profile_embedding=None)
            continue
        vec = encode_texts([text])[0]
        User.objects.filter(pk=user.pk).update(profile_embedding=to_list(vec))

    if stdout:
        stdout.write(
            f'Эмбеддинги обновлены: тегов {len(tags)}, проектов {len(projects)}.'
        )


class Command(BaseCommand):
    help = 'Пересчитывает эмбеддинги тегов, проектов и профилей студентов.'

    def handle(self, *args, **options):
        run_compute_embeddings(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('Готово.'))
