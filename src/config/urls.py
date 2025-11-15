# src/config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Подключаем URL-ы наших приложений
    path('users/', include('apps.users.urls', namespace='users')),
    path('projects/', include('apps.projects.urls', namespace='projects')),

    # Главная страница будет использовать наш шаблон home.html
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
]
