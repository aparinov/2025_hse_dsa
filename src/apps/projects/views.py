from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View

from .forms import ProjectForm, ProjectSearchForm
from .models import Application, Project, Tag
from .services_matching import propose_matching_for_teacher

UserModel = get_user_model()

class ProjectListView(ListView):
    """
    Представление для отображения списка активных проектов.
    """
    model = Project
    template_name = 'projects/project_list.html'
    context_object_name = 'project_list'
    paginate_by = 12  # 4 ряда по 3 карточки на десктопе
    search_form_class = ProjectSearchForm
    search_query_param = 'q'

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.active_tag = None
        raw_tag = request.GET.get('tag')
        if raw_tag and str(raw_tag).isdigit():
            self.active_tag = Tag.objects.filter(pk=int(raw_tag)).first()

    def get_queryset(self):
        """
        Исключаем из списка архивные проекты и оптимизируем запрос к БД.
        """
        queryset = super().get_queryset()
        queryset = queryset.exclude(status=Project.Status.ARCHIVED).select_related('creator').prefetch_related('tags')

        form = self.get_search_form()
        self.search_query = ''
        if form.is_valid():
            self.search_query = form.cleaned_data.get(self.search_query_param, '').strip()

        if self.search_query:
            if connection.vendor == 'sqlite':
                search_query = self.search_query.casefold()
                matching_ids = [
                    project_id
                    for project_id, title in queryset.values_list('pk', 'title')
                    if search_query in title.casefold()
                ]
                queryset = queryset.filter(pk__in=matching_ids)
            else:
                queryset = queryset.filter(title__icontains=self.search_query)

        if self.active_tag:
            queryset = queryset.filter(tags=self.active_tag).distinct()

        return queryset

    def get_search_form(self):
        """
        Возвращает форму поиска, привязанную к GET-параметрам.
        """
        if not hasattr(self, '_search_form'):
            self._search_form = self.search_form_class(self.request.GET)
        return self._search_form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = self.get_search_form()
        context['search_query'] = getattr(self, 'search_query', '')
        context['is_search_active'] = bool(context['search_query'])
        context['active_tag'] = self.active_tag
        params = []
        if context['search_query']:
            params.append(('q', context['search_query']))
        if self.active_tag:
            params.append(('tag', str(self.active_tag.pk)))
        context['filter_query'] = urlencode(params)
        return context


class TeacherDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Личный кабинет преподавателя - список созданных им проектов.
    Доступно только для пользователей с ролью 'Преподаватель'.
    """
    model = Project
    template_name = 'projects/teacher_dashboard.html'
    context_object_name = 'project_list'
    paginate_by = 10
    
    def test_func(self):
        """Проверяет, является ли пользователь преподавателем."""
        return self.request.user.is_teacher
    
    def get_queryset(self):
        """
        Возвращает проекты, созданные текущим преподавателем.
        Аннотирует количество необработанных заявок для каждого проекта.
        """
        queryset = super().get_queryset()
        return queryset.filter(
            creator=self.request.user
        ).select_related(
            'creator'
        ).prefetch_related(
            'tags', 'participants'
        ).annotate(
            pending_count=Count(
                'applications',
                filter=Q(applications__status=Application.Status.PENDING)
            )
        ).order_by('-created_at')


class StudentDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Личный кабинет студента - заявки и проекты, где он участвует.
    Доступно только для пользователей с ролью 'Студент'.
    """
    model = Application
    template_name = 'projects/student_dashboard.html'
    context_object_name = 'applications'
    
    def test_func(self):
        """Проверяет, является ли пользователь студентом."""
        return self.request.user.is_student
    
    def get_queryset(self):
        """
        Возвращает заявки текущего студента с оптимизацией запросов.
        """
        queryset = super().get_queryset()
        return queryset.filter(
            student=self.request.user
        ).select_related(
            'project__creator'
        ).prefetch_related(
            'project__tags'
        ).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        """
        Добавляет в контекст проекты, где студент является участником.
        """
        context = super().get_context_data(**kwargs)
        context['participating_projects'] = Project.objects.filter(
            participants=self.request.user
        ).select_related(
            'creator'
        ).prefetch_related(
            'tags'
        ).order_by('-created_at')
        return context


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
        return queryset.select_related('creator').prefetch_related('tags', 'participants', 'applications')
    
    def get_context_data(self, **kwargs):
        """Добавляем информацию о заявке текущего пользователя и счетчик заявок."""
        context = super().get_context_data(**kwargs)
        
        # Считаем количество заявок на рассмотрении (для преподавателя)
        context['pending_applications_count'] = self.object.applications.filter(
            status=Application.Status.PENDING
        ).count()
        
        # Проверяем заявку текущего пользователя (для студента)
        if self.request.user.is_authenticated:
            context['user_application'] = self.object.applications.filter(
                student=self.request.user
            ).first()
        
        return context


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


class ProjectUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Представление для редактирования проекта.
    Доступно только создателю проекта.
    """
    model = Project
    form_class = ProjectForm
    template_name = 'projects/project_form.html'
    
    def test_func(self):
        """Проверяет, что пользователь - создатель проекта."""
        project = self.get_object()
        return self.request.user == project.creator
    
    def get_success_url(self):
        """Перенаправляем на страницу проекта после обновления."""
        return reverse_lazy('projects:project-detail', kwargs={'pk': self.object.pk})


class ApplicationCreateView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для подачи заявки на участие в проекте.
    Доступно только для студентов.
    """
    
    def test_func(self):
        """Проверяет, что пользователь - студент."""
        return self.request.user.is_student
    
    def post(self, request, project_pk):
        """Обрабатывает подачу заявки."""
        project = get_object_or_404(Project, pk=project_pk)
        
        # Проверка: студент не может подать заявку на свой проект
        if project.creator == request.user:
            messages.error(request, 'Вы не можете подать заявку на собственный проект.')
            return redirect('projects:project-detail', pk=project_pk)
        
        # Проверка: студент уже участвует в проекте
        if project.participants.filter(pk=request.user.pk).exists():
            messages.info(request, 'Вы уже участвуете в этом проекте.')
            return redirect('projects:project-detail', pk=project_pk)
        
        # Проверка: студент уже подал заявку
        if Application.objects.filter(project=project, student=request.user).exists():
            messages.warning(request, 'Вы уже подали заявку на этот проект.')
            return redirect('projects:project-detail', pk=project_pk)
        
        # Создаем заявку
        Application.objects.create(
            project=project,
            student=request.user,
            status=Application.Status.PENDING
        )
        messages.success(request, 'Ваша заявка успешно отправлена!')
        
        return redirect('projects:project-detail', pk=project_pk)


class ProposeMatchingView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Запускает алгоритм Гейла–Шепли по всем открытым проектам преподавателя
    и показывает предлагаемое распределение по текущим заявкам PENDING.
    """

    def test_func(self):
        project = get_object_or_404(Project, pk=self.kwargs.get('pk'))
        return self.request.user == project.creator

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        result = propose_matching_for_teacher(project.creator)
        if not result:
            messages.info(request, 'Нет заявок в статусе «На рассмотрении» для распределения.')
            return redirect('projects:manage-applications', pk=pk)
        lines = []
        for pid, sids in sorted(result.items()):
            title = Project.objects.filter(pk=pid).values_list('title', flat=True).first()
            names = []
            for sid in sids:
                u = UserModel.objects.filter(pk=sid).first()
                label = u.get_full_name() or u.username if u else str(sid)
                names.append(label)
            lines.append(f'{title}: {", ".join(names)}')
        messages.success(
            request,
            'Предложение стабильного распределения (Гейл–Шепли): ' + ' | '.join(lines),
        )
        return redirect('projects:manage-applications', pk=pk)


class ManageApplicationsView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Представление для управления заявками на проект.
    Доступно только создателю проекта (преподавателю).
    """
    model = Project
    template_name = 'projects/manage_applications.html'
    context_object_name = 'project'
    
    def test_func(self):
        """Проверяет, что пользователь - создатель проекта."""
        project = self.get_object()
        return self.request.user == project.creator
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получаем все заявки на проект, сортированные по статусу и дате
        context['applications'] = self.object.applications.select_related('student').order_by(
            'status', '-created_at'
        )
        return context


class ApproveApplicationView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для принятия заявки.
    Доступно только создателю проекта.
    """
    
    def test_func(self):
        """Проверяет, что пользователь - создатель проекта."""
        application = get_object_or_404(Application, pk=self.kwargs.get('pk'))
        return self.request.user == application.project.creator
    
    def post(self, request, pk):
        """Принимает заявку и добавляет студента в участники."""
        application = get_object_or_404(Application, pk=pk)
        project = application.project
        
        # Проверка: есть ли еще места в проекте
        if project.participants.count() >= project.max_participants:
            messages.error(request, 'В проекте больше нет свободных мест.')
            return redirect('projects:manage-applications', pk=project.pk)
        
        # Меняем статус заявки
        application.status = Application.Status.APPROVED
        application.save()
        
        # Добавляем студента в участники
        project.participants.add(application.student)
        
        messages.success(
            request, 
            f'Заявка от {application.student.get_full_name() or application.student.username} принята.'
        )
        
        # Проверяем, заполнены ли все места
        if project.participants.count() >= project.max_participants:
            project.status = Project.Status.IN_PROGRESS
            project.save()
            messages.info(request, 'Все места в проекте заполнены. Статус изменен на "В процессе".')
        
        return redirect('projects:manage-applications', pk=project.pk)


class RejectApplicationView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для отклонения заявки.
    Доступно только создателю проекта.
    """
    
    def test_func(self):
        """Проверяет, что пользователь - создатель проекта."""
        application = get_object_or_404(Application, pk=self.kwargs.get('pk'))
        return self.request.user == application.project.creator
    
    def post(self, request, pk):
        """Отклоняет заявку."""
        application = get_object_or_404(Application, pk=pk)
        project = application.project
        
        # Меняем статус заявки
        application.status = Application.Status.REJECTED
        application.save()
        
        messages.success(
            request,
            f'Заявка от {application.student.get_full_name() or application.student.username} отклонена.'
        )
        
        return redirect('projects:manage-applications', pk=project.pk)


class ArchiveProjectView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для архивации проекта.
    Доступно только создателю проекта.
    """
    
    def test_func(self):
        """Проверяет, что пользователь - создатель проекта."""
        project = get_object_or_404(Project, pk=self.kwargs.get('pk'))
        return self.request.user == project.creator
    
    def post(self, request, pk):
        """Переводит проект в статус ARCHIVED."""
        project = get_object_or_404(Project, pk=pk)
        
        # Меняем статус проекта на ARCHIVED
        project.status = Project.Status.ARCHIVED
        project.save()
        
        messages.success(
            request,
            f'Проект "{project.title}" успешно архивирован.'
        )
        
        return redirect('projects:teacher-dashboard')


class WithdrawApplicationView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для отзыва заявки студентом.
    Доступно только студенту, подавшему заявку.
    """
    
    def test_func(self):
        """Проверяет, что пользователь - студент и автор заявки."""
        application = get_object_or_404(Application, pk=self.kwargs.get('pk'))
        return self.request.user.is_student and self.request.user == application.student
    
    def post(self, request, pk):
        """Удаляет заявку студента."""
        application = get_object_or_404(Application, pk=pk)
        project_title = application.project.title
        
        # Удаляем заявку
        application.delete()
        
        messages.success(
            request,
            f'Ваша заявка на проект "{project_title}" успешно отозвана.'
        )
        
        return redirect('projects:student-dashboard')
