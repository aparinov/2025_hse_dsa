from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from .models import Tag, Project, Application
from .forms import ProjectForm
from .services import get_recommended_projects

User = get_user_model()


class TagModelTests(TestCase):
    """Юнит-тесты для модели Tag."""
    
    def test_tag_str_returns_name(self):
        """__str__ возвращает название тега."""
        tag = Tag.objects.create(name='Test Tag')
        self.assertEqual(str(tag), 'Test Tag')
    
    def test_tag_name_is_unique(self):
        """Имя тега должно быть уникальным."""
        Tag.objects.create(name='Unique Tag')
        with self.assertRaises(IntegrityError):
            Tag.objects.create(name='Unique Tag')


class ProjectModelTests(TestCase):
    """Юнит-тесты для модели Project."""
    
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
    
    def test_project_str_returns_title(self):
        """__str__ возвращает название проекта."""
        project = Project.objects.create(
            title='Test Project',
            description='Description',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.assertEqual(str(project), 'Test Project')
    
    def test_project_default_status_is_recruitment(self):
        """Статус по умолчанию - RECRUITMENT."""
        project = Project.objects.create(
            title='New Project',
            description='Description',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.assertEqual(project.status, Project.Status.RECRUITMENT)
    
    def test_project_get_absolute_url(self):
        """get_absolute_url возвращает корректный URL."""
        project = Project.objects.create(
            title='Test',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        expected_url = reverse('projects:project-detail', kwargs={'pk': project.pk})
        self.assertEqual(project.get_absolute_url(), expected_url)


class ApplicationModelTests(TestCase):
    """Юнит-тесты для модели Application."""
    
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Description',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
    
    def test_application_default_status_is_pending(self):
        """Статус заявки по умолчанию - PENDING."""
        application = Application.objects.create(
            project=self.project,
            student=self.student
        )
        self.assertEqual(application.status, Application.Status.PENDING)
    
    def test_application_unique_together_constraint(self):
        """Студент не может подать две заявки на один проект."""
        Application.objects.create(project=self.project, student=self.student)
        with self.assertRaises(IntegrityError):
            Application.objects.create(project=self.project, student=self.student)


class ProjectFormTests(TestCase):
    """Юнит-тесты для формы ProjectForm."""
    
    def test_form_valid_with_correct_dates(self):
        """Форма валидна с корректными датами."""
        form = ProjectForm(data={
            'title': 'Test Project',
            'description': 'Description',
            'max_participants': 3,
            'application_deadline': date.today() + timedelta(days=7),
            'end_date': date.today() + timedelta(days=30),
            'tags': [],
            'milestones': ''
        })
        self.assertTrue(form.is_valid())
    
    def test_form_invalid_when_end_date_before_deadline(self):
        """Форма невалидна, если дата завершения раньше дедлайна."""
        form = ProjectForm(data={
            'title': 'Test Project',
            'description': 'Description',
            'max_participants': 3,
            'application_deadline': date.today() + timedelta(days=30),
            'end_date': date.today() + timedelta(days=7),
            'tags': [],
            'milestones': ''
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Дата завершения проекта должна быть позже', str(form.errors))
    
    def test_form_invalid_when_end_date_equals_deadline(self):
        """Форма невалидна, если дата завершения равна дедлайну."""
        same_date = date.today() + timedelta(days=10)
        form = ProjectForm(data={
            'title': 'Test Project',
            'description': 'Description',
            'max_participants': 3,
            'application_deadline': same_date,
            'end_date': same_date,
            'tags': [],
            'milestones': ''
        })
        self.assertFalse(form.is_valid())


class RecommendationServiceTests(TestCase):
    """Юнит-тесты для сервиса рекомендаций."""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        
        self.tag_ml = Tag.objects.create(name='Machine Learning')
        self.tag_web = Tag.objects.create(name='Web Development')
        self.tag_data = Tag.objects.create(name='Data Science')
        
        self.student.interests.add(self.tag_ml, self.tag_data)
    
    def test_returns_empty_queryset_for_user_without_interests(self):
        """Возвращает пустой QuerySet для пользователя без интересов."""
        user_no_interests = User.objects.create_user(
            username='nointerests',
            password='testpass123',
            role=User.Role.STUDENT
        )
        result = get_recommended_projects(user_no_interests)
        self.assertEqual(result.count(), 0)
    
    def test_returns_projects_with_matching_tags(self):
        """Возвращает проекты с совпадающими тегами."""
        project = Project.objects.create(
            title='ML Project',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project.tags.add(self.tag_ml)
        
        result = get_recommended_projects(self.student)
        self.assertIn(project, result)
    
    def test_excludes_projects_where_user_is_creator(self):
        """Исключает проекты, где пользователь - создатель."""
        teacher_with_interests = User.objects.create_user(
            username='teacher2',
            password='testpass123',
            role=User.Role.TEACHER
        )
        teacher_with_interests.interests.add(self.tag_ml)
        
        own_project = Project.objects.create(
            title='Own Project',
            description='Desc',
            creator=teacher_with_interests,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        own_project.tags.add(self.tag_ml)
        
        result = get_recommended_projects(teacher_with_interests)
        self.assertNotIn(own_project, result)
    
    def test_excludes_projects_where_user_is_participant(self):
        """Исключает проекты, где пользователь уже участвует."""
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project.tags.add(self.tag_ml)
        project.participants.add(self.student)
        
        result = get_recommended_projects(self.student)
        self.assertNotIn(project, result)
    
    def test_only_includes_recruitment_status_projects(self):
        """Включает только проекты со статусом RECRUITMENT."""
        project_completed = Project.objects.create(
            title='Completed',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.COMPLETED,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project_completed.tags.add(self.tag_ml)
        
        result = get_recommended_projects(self.student)
        self.assertNotIn(project_completed, result)
    
    def test_sorts_by_matching_tags_count(self):
        """Сортирует проекты по количеству совпадающих тегов."""
        project_one_tag = Project.objects.create(
            title='One Tag',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project_one_tag.tags.add(self.tag_ml)
        
        project_two_tags = Project.objects.create(
            title='Two Tags',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project_two_tags.tags.add(self.tag_ml, self.tag_data)
        
        result = list(get_recommended_projects(self.student))
        self.assertEqual(result[0], project_two_tags)
        self.assertEqual(result[1], project_one_tag)

    def test_uses_cover_letter_similarity(self):
        """Рекомендует проект по текстовой близости cover letter и описания."""
        student = User.objects.create_user(
            username='semantic',
            password='testpass123',
            role=User.Role.STUDENT,
            cover_letter='Хочу заниматься анализом данных и машинным обучением в продуктовых задачах.',
        )
        matching = Project.objects.create(
            title='Data Product',
            description='Проект про анализ данных, продуктовые метрики и машинное обучение.',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        other = Project.objects.create(
            title='Legal Research',
            description='Проект по исследованию правовых практик и архивных источников.',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )

        result = list(get_recommended_projects(student))
        self.assertEqual(result[0], matching)
        self.assertNotIn(other, result[:1])

    def test_uses_peer_applications_for_students_with_similar_tags(self):
        """Учитывает популярные проекты среди студентов с похожими тегами."""
        peer = User.objects.create_user(
            username='peer',
            password='testpass123',
            role=User.Role.STUDENT,
        )
        peer.interests.add(self.tag_ml, self.tag_data)
        popular = Project.objects.create(
            title='Popular ML Project',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        Application.objects.create(
            project=popular,
            student=peer,
            status=Application.Status.APPROVED,
        )

        result = get_recommended_projects(self.student)
        self.assertIn(popular, result)

    def test_uses_grades_when_project_tags_match_grade_domains(self):
        """Учитывает оценки студента по доменам, совпадающим с тегами проекта."""
        graded_student = User.objects.create_user(
            username='graded',
            password='testpass123',
            role=User.Role.STUDENT,
            grades_json={'Machine Learning': 10, 'Web Development': 5},
        )
        strong_match = Project.objects.create(
            title='ML Research',
            description='Исследовательский проект по машинному обучению.',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        strong_match.tags.add(self.tag_ml)

        weak_match = Project.objects.create(
            title='Web Platform',
            description='Разработка веб-платформы.',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        weak_match.tags.add(self.tag_web)

        result = list(get_recommended_projects(graded_student))
        self.assertEqual(result[0], strong_match)


class ProjectListViewTests(TestCase):
    """Интеграционные тесты для списка проектов."""
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('projects:project-list')
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
    
    def _create_project(self, title, status=Project.Status.RECRUITMENT):
        return Project.objects.create(
            title=title,
            description='Desc',
            creator=self.teacher,
            status=status,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
    
    def test_project_list_page_renders(self):
        """Страница списка проектов корректно отображается."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_list.html')
    
    def test_excludes_archived_projects_from_list(self):
        """Архивные проекты не отображаются в списке."""
        active_project = Project.objects.create(
            title='Active',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.RECRUITMENT,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        archived_project = Project.objects.create(
            title='Archived',
            description='Desc',
            creator=self.teacher,
            status=Project.Status.ARCHIVED,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        
        response = self.client.get(self.url)
        self.assertIn(active_project, response.context['project_list'])
        self.assertNotIn(archived_project, response.context['project_list'])

    def test_search_filters_projects_by_title(self):
        """Поиск возвращает проекты, содержащие запрос в названии."""
        matching = self._create_project('Рекомендательная система для науки')
        non_matching = self._create_project('Система мониторинга качества')

        response = self.client.get(self.url, {'q': 'рекомендательная'})

        project_list = list(response.context['project_list'])
        self.assertIn(matching, project_list)
        self.assertNotIn(non_matching, project_list)

    def test_search_is_case_insensitive(self):
        """Поиск не зависит от регистра."""
        project = self._create_project('Data Platform')

        response = self.client.get(self.url, {'q': 'data platform'})

        self.assertIn(project, response.context['project_list'])

    def test_search_does_not_return_archived_projects(self):
        """Даже совпадающие по названию архивные проекты не отображаются."""
        archived = self._create_project(
            'Архивный рекомендательный проект',
            status=Project.Status.ARCHIVED
        )
        active = self._create_project('Активный рекомендательный проект')

        response = self.client.get(self.url, {'q': 'рекомендательный'})

        project_list = list(response.context['project_list'])
        self.assertIn(active, project_list)
        self.assertNotIn(archived, project_list)

    def test_search_context_flags_are_set(self):
        """Контекст содержит информацию о поисковом запросе."""
        self._create_project('Test Project')

        response = self.client.get(self.url, {'q': 'test'})

        self.assertTrue(response.context['is_search_active'])
        self.assertEqual(response.context['search_query'], 'test')

    def test_tag_filter_shows_only_matching_projects(self):
        """Фильтр ?tag=<id> показывает проекты с этим тегом."""
        from apps.projects.models import Tag

        tag_ml = Tag.objects.create(name='Machine Learning')
        tag_web = Tag.objects.create(name='Web Development')
        ml_project = self._create_project('ML Research')
        ml_project.tags.add(tag_ml)
        web_project = self._create_project('Web App')
        web_project.tags.add(tag_web)

        response = self.client.get(self.url, {'tag': str(tag_ml.pk)})
        project_list = list(response.context['project_list'])
        self.assertIn(ml_project, project_list)
        self.assertNotIn(web_project, project_list)
        self.assertEqual(response.context['active_tag'], tag_ml)


class ProjectDetailViewTests(TestCase):
    """Интеграционные тесты для страницы проекта."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Description',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.url = reverse('projects:project-detail', kwargs={'pk': self.project.pk})
    
    def test_project_detail_page_renders(self):
        """Страница проекта корректно отображается."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_detail.html')
        self.assertContains(response, 'Test Project')
    
    def test_shows_project_details_in_html(self):
        """HTML содержит детали проекта."""
        response = self.client.get(self.url)
        self.assertContains(response, self.project.title)
        self.assertContains(response, self.project.description)


class ProjectUpdateViewTests(TestCase):
    """Интеграционные тесты для редактирования проекта."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username='other_teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Description',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.url = reverse('projects:project-update', kwargs={'pk': self.project.pk})
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_creator_can_edit_own_project(self):
        """Создатель проекта может редактировать свой проект."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_other_teacher_cannot_edit_project(self):
        """Другой преподаватель не может редактировать чужой проект."""
        self.client.login(username='other_teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_student_cannot_edit_project(self):
        """Студент не может редактировать проект."""
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_creator_can_update_project_data(self):
        """Создатель может обновить данные проекта."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url, {
            'title': 'Updated Title',
            'description': 'Updated Description',
            'max_participants': 5,
            'application_deadline': date.today() + timedelta(days=10),
            'end_date': date.today() + timedelta(days=40),
            'milestones': 'Updated milestones'
        })
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'Updated Title')
        self.assertEqual(self.project.description, 'Updated Description')


class Project404Tests(TestCase):
    """Тесты на обработку несуществующих объектов."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
    
    def test_nonexistent_project_returns_404(self):
        """Запрос несуществующего проекта возвращает 404."""
        url = reverse('projects:project-detail', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
    
    def test_nonexistent_project_update_returns_404(self):
        """Редактирование несуществующего проекта возвращает 404."""
        self.client.login(username='teacher', password='testpass123')
        url = reverse('projects:project-update', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class ProjectCreateViewTests(TestCase):
    """Интеграционные тесты для создания проекта."""
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('projects:project-create')
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_student_cannot_access_create_project_page(self):
        """Студент не может создать проект (403)."""
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_teacher_can_access_create_project_page(self):
        """Преподаватель может открыть страницу создания проекта."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_form.html')
    
    def test_teacher_can_create_project(self):
        """Преподаватель может создать проект через POST."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url, {
            'title': 'New Project',
            'description': 'Project description',
            'max_participants': 5,
            'application_deadline': date.today() + timedelta(days=7),
            'end_date': date.today() + timedelta(days=30),
            'milestones': ''
        })
        
        self.assertEqual(Project.objects.count(), 1)
        project = Project.objects.first()
        self.assertEqual(project.title, 'New Project')
        self.assertEqual(project.creator, self.teacher)
        self.assertRedirects(response, project.get_absolute_url())


class ApplicationCreateViewTests(TestCase):
    """Интеграционные тесты для подачи заявки."""
    
    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.url = reverse('projects:application-create', kwargs={'project_pk': self.project.pk})
    
    def test_anonymous_user_cannot_apply(self):
        """Анонимный пользователь не может подать заявку."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_teacher_cannot_apply_to_project(self):
        """Преподаватель не может подать заявку (403)."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_student_participant_cannot_apply_again(self):
        """Студент-участник проекта не может подать заявку."""
        # Добавляем студента в участники напрямую
        self.project.participants.add(self.student)
        
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        
        # Проверяем сообщение
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('уже участвуете' in str(m) for m in messages))
    
    def test_student_can_apply_to_project(self):
        """Студент может подать заявку на проект."""
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        
        self.assertEqual(Application.objects.count(), 1)
        application = Application.objects.first()
        self.assertEqual(application.project, self.project)
        self.assertEqual(application.student, self.student)
        self.assertEqual(application.status, Application.Status.PENDING)
        self.assertRedirects(response, self.project.get_absolute_url())
    
    def test_student_cannot_apply_twice_to_same_project(self):
        """Студент не может подать две заявки на один проект."""
        self.client.login(username='student', password='testpass123')
        
        # Первая заявка
        first_response = self.client.post(self.url)
        self.assertEqual(first_response.status_code, 302)
        initial_count = Application.objects.count()
        self.assertEqual(initial_count, 1)
        
        # Вторая заявка на тот же проект - должна быть отклонена
        second_response = self.client.post(self.url)
        
        # Проверяем, что показывается правильное сообщение об ошибке
        messages = list(second_response.wsgi_request._messages)
        self.assertTrue(any('уже подали заявку' in str(m) for m in messages))
        
        # Проверяем редирект обратно на страницу проекта
        self.assertRedirects(second_response, self.project.get_absolute_url())


class ManageApplicationsViewTests(TestCase):
    """Интеграционные тесты для управления заявками."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username='other',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.url = reverse('projects:manage-applications', kwargs={'pk': self.project.pk})
    
    def test_only_project_creator_can_access(self):
        """Только создатель проекта может управлять заявками."""
        self.client.login(username='other', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_project_creator_can_access(self):
        """Создатель проекта может просмотреть заявки."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/manage_applications.html')


class ApproveApplicationViewTests(TestCase):
    """Интеграционные тесты для принятия заявки."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test',
            description='Desc',
            creator=self.teacher,
            max_participants=2,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.application = Application.objects.create(
            project=self.project,
            student=self.student
        )
        self.url = reverse('projects:application-approve', kwargs={'pk': self.application.pk})
    
    def test_approve_application_changes_status(self):
        """Принятие заявки меняет ее статус на APPROVED."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.APPROVED)
    
    def test_approve_application_adds_student_to_participants(self):
        """Принятие заявки добавляет студента в участники проекта."""
        self.client.login(username='teacher', password='testpass123')
        self.client.post(self.url)
        
        self.assertIn(self.student, self.project.participants.all())
    
    def test_project_status_changes_when_full(self):
        """Статус проекта меняется на IN_PROGRESS когда все места заполнены."""
        student2 = User.objects.create_user(
            username='student2',
            password='testpass123',
            role=User.Role.STUDENT
        )
        application2 = Application.objects.create(
            project=self.project,
            student=student2
        )
        
        self.client.login(username='teacher', password='testpass123')
        self.client.post(self.url)
        self.client.post(reverse('projects:application-approve', kwargs={'pk': application2.pk}))
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.IN_PROGRESS)


class RejectApplicationViewTests(TestCase):
    """Интеграционные тесты для отклонения заявки."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.application = Application.objects.create(
            project=self.project,
            student=self.student
        )
        self.url = reverse('projects:application-reject', kwargs={'pk': self.application.pk})
    
    def test_reject_application_changes_status(self):
        """Отклонение заявки меняет ее статус на REJECTED."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.REJECTED)
    
    def test_reject_application_does_not_add_to_participants(self):
        """Отклоненная заявка не добавляет студента в участники."""
        self.client.login(username='teacher', password='testpass123')
        self.client.post(self.url)
        
        self.assertNotIn(self.student, self.project.participants.all())


class TeacherDashboardViewTests(TestCase):
    """Интеграционные тесты для личного кабинета преподавателя."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username='other_teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.url = reverse('projects:teacher-dashboard')
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_student_cannot_access_dashboard(self):
        """Студент не может получить доступ к личному кабинету преподавателя."""
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_teacher_can_access_dashboard(self):
        """Преподаватель может открыть свой личный кабинет."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/teacher_dashboard.html')
    
    def test_displays_only_teacher_own_projects(self):
        """Личный кабинет показывает только проекты текущего преподавателя."""
        own_project = Project.objects.create(
            title='Own Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        other_project = Project.objects.create(
            title='Other Project',
            description='Desc',
            creator=self.other_teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertIn(own_project, response.context['project_list'])
        self.assertNotIn(other_project, response.context['project_list'])
    
    def test_annotates_pending_applications_count(self):
        """Проекты аннотированы количеством необработанных заявок."""
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        student1 = User.objects.create_user(
            username='student1',
            password='testpass123',
            role=User.Role.STUDENT
        )
        student2 = User.objects.create_user(
            username='student2',
            password='testpass123',
            role=User.Role.STUDENT
        )
        
        # Создаем заявки с разными статусами
        Application.objects.create(
            project=project,
            student=student1,
            status=Application.Status.PENDING
        )
        Application.objects.create(
            project=project,
            student=student2,
            status=Application.Status.APPROVED
        )
        Application.objects.create(
            project=project,
            student=self.student,
            status=Application.Status.PENDING
        )
        
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        
        project_in_list = response.context['project_list'][0]
        # Должно быть только 2 PENDING заявки
        self.assertEqual(project_in_list.pending_count, 2)
    
    def test_empty_dashboard_when_no_projects(self):
        """Личный кабинет показывает сообщение, когда нет проектов."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['project_list']), 0)
    
    def test_projects_ordered_by_creation_date(self):
        """Проекты сортируются по дате создания (новые первыми)."""
        project1 = Project.objects.create(
            title='First Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project2 = Project.objects.create(
            title='Second Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        
        project_list = list(response.context['project_list'])
        self.assertEqual(project_list[0], project2)
        self.assertEqual(project_list[1], project1)


class StudentDashboardViewTests(TestCase):
    """Интеграционные тесты для личного кабинета студента."""
    
    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.url = reverse('projects:student-dashboard')
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_teacher_cannot_access_student_dashboard(self):
        """Преподаватель не может получить доступ к личному кабинету студента."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_student_can_access_dashboard(self):
        """Студент может открыть свой личный кабинет."""
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/student_dashboard.html')
    
    def test_displays_student_applications(self):
        """Личный кабинет показывает заявки студента."""
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        application = Application.objects.create(
            project=project,
            student=self.student,
            status=Application.Status.PENDING
        )
        
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertIn(application, response.context['applications'])
    
    def test_does_not_display_other_students_applications(self):
        """Личный кабинет не показывает заявки других студентов."""
        other_student = User.objects.create_user(
            username='other_student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        own_application = Application.objects.create(
            project=project,
            student=self.student,
            status=Application.Status.PENDING
        )
        other_application = Application.objects.create(
            project=project,
            student=other_student,
            status=Application.Status.PENDING
        )
        
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertIn(own_application, response.context['applications'])
        self.assertNotIn(other_application, response.context['applications'])
    
    def test_displays_participating_projects(self):
        """Личный кабинет показывает проекты, где студент участвует."""
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project.participants.add(self.student)
        
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertIn(project, response.context['participating_projects'])
    
    def test_does_not_display_projects_where_not_participant(self):
        """Не показывает проекты, где студент не участвует."""
        project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertNotIn(project, response.context['participating_projects'])
    
    def test_empty_dashboard_when_no_applications_or_projects(self):
        """Личный кабинет корректно отображается без заявок и проектов."""
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['applications']), 0)
        self.assertEqual(len(response.context['participating_projects']), 0)
    
    def test_applications_ordered_by_creation_date(self):
        """Заявки сортируются по дате создания (новые первыми)."""
        project1 = Project.objects.create(
            title='Project 1',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        project2 = Project.objects.create(
            title='Project 2',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        
        application1 = Application.objects.create(
            project=project1,
            student=self.student
        )
        application2 = Application.objects.create(
            project=project2,
            student=self.student
        )
        
        self.client.login(username='student', password='testpass123')
        response = self.client.get(self.url)
        
        applications_list = list(response.context['applications'])
        self.assertEqual(applications_list[0], application2)
        self.assertEqual(applications_list[1], application1)


class ArchiveProjectViewTests(TestCase):
    """Интеграционные тесты для архивации проекта."""
    
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username='other_teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.url = reverse('projects:project-archive', kwargs={'pk': self.project.pk})
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_only_creator_can_archive_project(self):
        """Только создатель проекта может его архивировать."""
        self.client.login(username='other_teacher', password='testpass123')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_student_cannot_archive_project(self):
        """Студент не может архивировать проект."""
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_creator_can_archive_project(self):
        """Создатель может архивировать свой проект."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ARCHIVED)
    
    def test_archive_redirects_to_teacher_dashboard(self):
        """После архивации происходит редирект в личный кабинет."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        
        self.assertRedirects(response, reverse('projects:teacher-dashboard'))
    
    def test_archive_shows_success_message(self):
        """После архивации показывается сообщение об успехе."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('архивирован' in str(m) for m in messages))
    
    def test_archived_project_not_in_general_list(self):
        """Архивный проект не отображается в общем списке."""
        self.client.login(username='teacher', password='testpass123')
        self.client.post(self.url)
        
        # Проверяем общий список проектов
        list_response = self.client.get(reverse('projects:project-list'))
        self.assertNotIn(self.project, list_response.context['project_list'])
    
    def test_archived_project_still_in_teacher_dashboard(self):
        """Архивный проект остается в личном кабинете преподавателя."""
        self.client.login(username='teacher', password='testpass123')
        self.client.post(self.url)
        
        # Проверяем личный кабинет
        dashboard_response = self.client.get(reverse('projects:teacher-dashboard'))
        self.assertIn(self.project, dashboard_response.context['project_list'])


class WithdrawApplicationViewTests(TestCase):
    """Интеграционные тесты для отзыва заявки студентом."""
    
    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username='other_student',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='testpass123',
            role=User.Role.TEACHER
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='Desc',
            creator=self.teacher,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30)
        )
        self.application = Application.objects.create(
            project=self.project,
            student=self.student,
            status=Application.Status.PENDING
        )
        self.url = reverse('projects:application-withdraw', kwargs={'pk': self.application.pk})
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_teacher_cannot_withdraw_application(self):
        """Преподаватель не может отозвать заявку студента."""
        self.client.login(username='teacher', password='testpass123')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_other_student_cannot_withdraw_application(self):
        """Другой студент не может отозвать чужую заявку."""
        self.client.login(username='other_student', password='testpass123')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
    
    def test_student_can_withdraw_own_application(self):
        """Студент может отозвать свою заявку."""
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        
        # Проверяем, что заявка удалена
        self.assertFalse(Application.objects.filter(pk=self.application.pk).exists())
    
    def test_withdraw_redirects_to_student_dashboard(self):
        """После отзыва происходит редирект в личный кабинет студента."""
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        
        self.assertRedirects(response, reverse('projects:student-dashboard'))
    
    def test_withdraw_shows_success_message(self):
        """После отзыва показывается сообщение об успехе."""
        self.client.login(username='student', password='testpass123')
        response = self.client.post(self.url)
        
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('отозвана' in str(m) for m in messages))
    
    def test_student_can_reapply_after_withdraw(self):
        """Студент может подать заявку повторно после отзыва."""
        self.client.login(username='student', password='testpass123')
        
        # Отзываем заявку
        self.client.post(self.url)
        
        # Подаем заявку заново
        apply_url = reverse('projects:application-create', kwargs={'project_pk': self.project.pk})
        response = self.client.post(apply_url)
        
        # Проверяем, что новая заявка создана
        self.assertEqual(Application.objects.filter(
            project=self.project,
            student=self.student
        ).count(), 1)

