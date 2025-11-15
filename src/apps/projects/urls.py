from django.urls import path
from .views import ProjectListView, ProjectDetailView, ProjectCreateView

app_name = 'projects'

urlpatterns = [
    # Список проектов
    path('', ProjectListView.as_view(), name='project-list'),
    
    # Создание проекта
    path('create/', ProjectCreateView.as_view(), name='project-create'),
    
    # Детальная страница проекта
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
]

