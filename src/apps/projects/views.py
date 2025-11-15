from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView

from .forms import ProjectForm
from .models import Project

class ProjectListView(ListView):
    """
    Представление для отображения списка активных проектов.
    """
    model = Project
    template_name = 'projects/project_list.html'
    context_object_name = 'project_list'
    paginate_by = 10  # Показываем 10 проектов на странице

    def get_queryset(self):
        """
        Исключаем из списка архивные проекты и оптимизируем запрос к БД.
        """
        queryset = super().get_queryset()
        return queryset.exclude(status=Project.Status.ARCHIVED).select_related('creator').prefetch_related('tags')


class ProjectDetailView(DetailView):
    """
    Представление для детального просмотра одного проекта.
    """
    model = Project
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        """Оптимизируем запрос к БД, подгружая связанные данные."""
        queryset = super().get_queryset()
        return queryset.select_related('creator').prefetch_related('tags', 'participants')


class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Представление для создания нового проекта.
    Доступно только для пользователей с ролью 'Преподаватель'.
    """
    model = Project
    form_class = ProjectForm
    template_name = 'projects/project_form.html'

    def test_func(self):
        """
        Проверяет, является ли пользователь преподавателем.
        UserPassesTestMixin вызовет этот метод.
        """
        return self.request.user.is_teacher

    def form_valid(self, form):
        """
        Присваиваем текущего пользователя как создателя проекта
        перед сохранением формы.
        """
        form.instance.creator = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        """
        Перенаправляем пользователя на страницу созданного проекта
        после успешного создания.
        """
        return reverse_lazy('projects:project-detail', kwargs={'pk': self.object.pk})
