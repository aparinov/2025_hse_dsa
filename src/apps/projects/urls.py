from django.urls import path
from .views import (
    ProjectListView, ProjectDetailView, ProjectCreateView, ProjectUpdateView,
    ApplicationCreateView, ManageApplicationsView,
    ApproveApplicationView, RejectApplicationView, TeacherDashboardView,
    StudentDashboardView, ArchiveProjectView, WithdrawApplicationView
)

app_name = 'projects'

urlpatterns = [
    # Список проектов
    path('', ProjectListView.as_view(), name='project-list'),
    
    # Личный кабинет преподавателя
    path('my-projects/', TeacherDashboardView.as_view(), name='teacher-dashboard'),
    
    # Личный кабинет студента
    path('my-applications/', StudentDashboardView.as_view(), name='student-dashboard'),
    
    # Создание проекта
    path('create/', ProjectCreateView.as_view(), name='project-create'),
    
    # Детальная страница проекта
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    
    # Редактирование проекта
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project-update'),
    
    # Архивация проекта
    path('<int:pk>/archive/', ArchiveProjectView.as_view(), name='project-archive'),
    
    # Подача заявки на проект
    path('<int:project_pk>/apply/', ApplicationCreateView.as_view(), name='application-create'),
    
    # Управление заявками (для преподавателя)
    path('<int:pk>/applications/', ManageApplicationsView.as_view(), name='manage-applications'),
    
    # Принятие заявки
    path('applications/<int:pk>/approve/', ApproveApplicationView.as_view(), name='application-approve'),
    
    # Отклонение заявки
    path('applications/<int:pk>/reject/', RejectApplicationView.as_view(), name='application-reject'),
    
    # Отзыв заявки студентом
    path('applications/<int:pk>/withdraw/', WithdrawApplicationView.as_view(), name='application-withdraw'),
]

