# src/config/urls.py

from django.contrib import admin
from django.urls import path, include
from apps.core.views import HomeView

urlpatterns = [                 
    path('admin/', admin.site.urls),
    
    # Подключаем URL-ы наших приложений
    path('users/', include('apps.users.urls', namespace='users')),
    path('projects/', include('apps.projects.urls', namespace='projects')),

    # Главная страница с блоком рекомендованных проектов
    path('', HomeView.as_view(), name='home'),
]
