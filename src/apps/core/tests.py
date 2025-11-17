from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from apps.projects.models import Project, Tag
from apps.users.models import User


class HomeViewTests(TestCase):
    """Интеграционные тесты для главной страницы и блока рекомендаций."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("home")

        self.teacher = User.objects.create_user(
            username="teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )

        self.student = User.objects.create_user(
            username="student",
            password="testpass123",
            role=User.Role.STUDENT,
        )

        self.tag_ml = Tag.objects.create(name="Machine Learning")
        self.tag_web = Tag.objects.create(name="Web Development")

    def _create_project(self, title, tags=None, status=Project.Status.RECRUITMENT):
        project = Project.objects.create(
            title=title,
            description="Desc",
            creator=self.teacher,
            status=status,
            application_deadline=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=30),
        )
        if tags:
            project.tags.add(*tags)
        return project

    def test_home_page_renders(self):
        """Главная страница успешно открывается для гостя."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_guest_sees_fallback_recruitment_projects(self):
        """Гость видит fallback-проекты со статусом RECRUITMENT."""
        project_active = self._create_project("Active", tags=[self.tag_ml])
        self._create_project("Archived", status=Project.Status.ARCHIVED)

        response = self.client.get(self.url)
        projects = response.context["recommended_projects"]

        self.assertIn(project_active, projects)
        self.assertTrue(all(p.status == Project.Status.RECRUITMENT for p in projects))

    def test_student_with_interests_sees_personal_recommendations(self):
        """Студент с интересами видит проекты с совпадающими тегами."""
        self.student.interests.add(self.tag_ml)
        matching = self._create_project("ML Project", tags=[self.tag_ml])
        non_matching = self._create_project("Web Project", tags=[self.tag_web])

        self.client.login(username="student", password="testpass123")
        response = self.client.get(self.url)

        projects = response.context["recommended_projects"]
        self.assertIn(matching, projects)
        self.assertNotIn(non_matching, projects)

    def test_student_without_interests_falls_back_to_default_list(self):
        """Студент без интересов получает fallback-список проектов."""
        fallback_project = self._create_project("Fallback", tags=[self.tag_ml])

        self.client.login(username="student", password="testpass123")
        response = self.client.get(self.url)

        projects = response.context["recommended_projects"]
        self.assertIn(fallback_project, projects)


