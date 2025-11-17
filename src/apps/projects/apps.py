from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    """Конфигурация приложения projects."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.projects'
    verbose_name = 'Проекты'

