from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.projects.models import Tag

User = get_user_model()


class UserModelTests(TestCase):
    """Юнит-тесты для модели User."""
    
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
    
    def test_is_student_property_returns_true_for_student(self):
        """Свойство is_student возвращает True для студента."""
        self.assertTrue(self.student.is_student)
    
    def test_is_student_property_returns_false_for_teacher(self):
        """Свойство is_student возвращает False для преподавателя."""
        self.assertFalse(self.teacher.is_student)
    
    def test_is_teacher_property_returns_true_for_teacher(self):
        """Свойство is_teacher возвращает True для преподавателя."""
        self.assertTrue(self.teacher.is_teacher)
    
    def test_is_teacher_property_returns_false_for_student(self):
        """Свойство is_teacher возвращает False для студента."""
        self.assertFalse(self.student.is_teacher)
    
    def test_user_str_returns_full_name_when_available(self):
        """__str__ возвращает полное имя, если оно есть."""
        self.student.first_name = 'Иван'
        self.student.last_name = 'Иванов'
        self.student.save()
        self.assertEqual(str(self.student), 'Иван Иванов')
    
    def test_user_str_returns_username_when_no_full_name(self):
        """__str__ возвращает username, если полного имени нет."""
        self.assertEqual(str(self.student), 'student')


class UserProfileFormTests(TestCase):
    """Юнит-тесты для формы профиля пользователя."""
    
    def setUp(self):
        from apps.users.forms import UserProfileForm
        self.form_class = UserProfileForm
        self.tag1 = Tag.objects.create(name='Machine Learning')
        self.tag2 = Tag.objects.create(name='Web Development')
    
    def test_valid_form_data(self):
        """Форма валидна с корректными данными."""
        form = self.form_class(data={
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'campus': 'Москва',
            'program': 'Программная инженерия',
            'study_year': 2,
            'degree_level': User.DegreeLevel.BACHELOR,
            'bio': 'Тестовая биография',
            'cover_letter': 'Хочу заниматься ML-проектами.',
            'contacts': 'ivan@example.com',
            'interests': [self.tag1.id],
            'grades_json': '{"Machine Learning": 8}',
        })
        self.assertTrue(form.is_valid())
    
    def test_form_allows_empty_optional_fields(self):
        """Форма валидна с пустыми необязательными полями."""
        form = self.form_class(data={
            'first_name': '',
            'last_name': '',
            'campus': '',
            'program': '',
            'study_year': '',
            'degree_level': '',
            'bio': '',
            'cover_letter': '',
            'contacts': '',
            'interests': [],
            'grades_json': '',
        })
        self.assertTrue(form.is_valid())


class SignUpViewTests(TestCase):
    """Интеграционные тесты для регистрации пользователя."""
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('users:signup')
    
    def test_signup_page_renders_correctly(self):
        """Страница регистрации корректно отображается."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/signup.html')
    
    def test_signup_creates_new_user(self):
        """POST-запрос создает нового пользователя."""
        response = self.client.post(self.url, {
            'username': 'newuser',
            'first_name': 'Новый',
            'last_name': 'Пользователь',
            'email': 'new@example.com',
            'role': User.Role.STUDENT,
            'password1': 'SecurePass123',
            'password2': 'SecurePass123'
        })
        
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.username, 'newuser')
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertRedirects(response, reverse('users:login'))
    
    def test_signup_with_invalid_data_shows_errors(self):
        """Регистрация с невалидными данными показывает ошибки."""
        response = self.client.post(self.url, {
            'username': 'test',
            'password1': '123',
            'password2': '456'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertEqual(User.objects.count(), 0)


class ProfileViewTests(TestCase):
    """Интеграционные тесты для страницы профиля."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role=User.Role.STUDENT
        )
        self.url = reverse('users:profile')
        self.tag1 = Tag.objects.create(name='Data Science')
    
    def test_anonymous_user_redirected_to_login(self):
        """Анонимный пользователь перенаправляется на логин."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def test_authenticated_user_can_view_profile(self):
        """Авторизованный пользователь может просмотреть свой профиль."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/profile.html')
        self.assertEqual(response.context['object'], self.user)
    
    def test_user_can_update_profile(self):
        """Пользователь может обновить свой профиль."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(self.url, {
            'first_name': 'Обновленное',
            'last_name': 'Имя',
            'campus': 'Москва',
            'program': 'Анализ данных',
            'study_year': 1,
            'degree_level': User.DegreeLevel.MASTER,
            'bio': 'Новая биография',
            'cover_letter': 'Интересуют прикладные исследовательские проекты.',
            'contacts': 'new@example.com',
            'interests': [self.tag1.id],
            'grades_json': '{"Data Science": 9}',
        })
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Обновленное')
        self.assertEqual(self.user.bio, 'Новая биография')
        self.assertEqual(self.user.program, 'Анализ данных')
        self.assertEqual(self.user.grades_json, {'Data Science': 9})
        self.assertIn(self.tag1, self.user.interests.all())
        self.assertRedirects(response, self.url)

