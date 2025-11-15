from django.urls import path
from .views import (
    ProjectListView, ProjectDetailView, ProjectCreateView,
    ApplicationCreateView, ManageApplicationsView,
    ApproveApplicationView, RejectApplicationView
)

app_name = 'projects'

urlpatterns = [
    # Список проектов
    path('', ProjectListView.as_view(), name='project-list'),
    
    # Создание проекта
    path('create/', ProjectCreateView.as_view(), name='project-create'),
    
    # Детальная страница проекта
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    
    # Подача заявки на проект
    path('<int:project_pk>/apply/', ApplicationCreateView.as_view(), name='application-create'),
    
    # Управление заявками (для преподавателя)
    path('<int:pk>/applications/', ManageApplicationsView.as_view(), name='manage-applications'),
    
    # Принятие заявки
    path('applications/<int:pk>/approve/', ApproveApplicationView.as_view(), name='application-approve'),
    
    # Отклонение заявки
    path('applications/<int:pk>/reject/', RejectApplicationView.as_view(), name='application-reject'),
]

