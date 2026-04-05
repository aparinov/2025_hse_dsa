import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

def pytest_configure(config):
    """Настройка Django для pytest."""
    if not settings.configured:
        django.setup()

