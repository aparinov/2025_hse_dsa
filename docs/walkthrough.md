# Объяснение структуры проекта и модулей
_Exported on 11/16/2025 at 13:28:59 GMT+3 from Cursor (1.7.39)_

---

**User**

Ты — опытный Full-Stack разработчик с глубокой экспертизой в Python и Django. Твоя задача — помочь в создании MVP платформы студенческих проектов. Ты прагматичен, пишешь чистый, документированный код и всегда фокусируешься на требованиях MVP, избегая излишнего усложнения. Ты работаешь в команде с двумя другими разработчиками.

Вводные по проекту ты можешь изучить в файлах @Требования.md и @README.md

**1. ОБЩАЯ ЦЕЛЬ ПРОЕКТА (MISSION)**

Создать быстрый, надежный и функциональный MVP двусторонней платформы, где преподаватели создают проекты, а студенты подают на них заявки. Главные приоритеты: скорость разработки, простота поддержки и стабильная основа для будущего развития.

**2. АРХИТЕКТУРНЫЕ ПРИНЦИПЫ (MUST FOLLOW)**

*   **Архитектура:** Строгий "Величественный Монолит" (Majestic Monolith). Никаких микросервисов.
*   **Клиент:** Единое веб-приложение с рендерингом на стороне сервера (Server-Side Rendering). **Никаких отдельных Frontend-фреймворков (React, Vue) или SPA.**
*   **База данных:** PostgreSQL — единственный источник данных.
*   **Ролевая модель:** Функционал внутри единого приложения разграничивается на основе роли пользователя (Студент, Преподаватель).
*   **Развертывание:** Приложение должно быть полностью контейнеризировано с помощью Docker и Docker Compose для унификации окружения разработки и продакшена.

**3. ТЕХНОЛОГИЧЕСКИЙ СТЕК (STRICTLY USE)**

*   **Backend:** Python 3.10+, Django 4+
*   **База данных:** PostgreSQL 14+
*   **WSGI Server:** Gunicorn
*   **Frontend:** Django Templates, CSS-фреймворк Bootstrap 5 (используй его для быстрой и адаптивной верстки).
*   **Инструменты:** Docker, Docker Compose, Git.

**4. СТРУКТУРА ПРОЕКТА (ADHERE TO THIS STRUCTURE)**

Всегда следуй утвержденной структуре репозитория:
*   Исходный код находится в директории `src/`.
*   Django-приложения (`users`, `projects`) находятся внутри `src/apps/`.
*   Конфигурация Django — в `src/config/`.
*   Общие шаблоны — в `src/templates/`, статика — в `src/static/`.
*   Конфигурации Docker находятся в корневой папке и в `.docker/`.

**5. МОДЕЛИ ДАННЫХ (CORE ENTITIES)**

Это наш основной контракт по данным. Реализуй модели в точном соответствии с этой схемой:

```python
# users.models.User
# Наследуется от AbstractUser, добавляет поля:
# role (Choices: STUDENT, TEACHER)
# bio (TextField)
# contacts (CharField)
# interests (ManyToManyField to Tag)

# projects.models.Tag
# name (CharField, unique)

# projects.models.Project
# title (CharField)
# description (TextField)
# creator (ForeignKey to User)
# status (Choices: RECRUITMENT, IN_PROGRESS, COMPLETED, ARCHIVED)
# max_participants (PositiveIntegerField)
# application_deadline (DateField)
# end_date (DateField)
# tags (ManyToManyField to Tag)
# participants (ManyToManyField to User)
# milestones (TextField)

# projects.models.Application
# project (ForeignKey to Project)
# student (ForeignKey to User)
# status (Choices: PENDING, APPROVED, REJECTED)
# Meta: unique_together = ('project', 'student')
```

**6. КЛЮЧЕВЫЕ БИЗНЕС-ПРОЦЕССЫ**

*   **Регистрация:** Простая, по email/паролю с выбором роли.
*   **Создание проекта:** Доступно только для роли `TEACHER`.
*   **Подача заявки:** Доступно только для роли `STUDENT`. Студент не может подать больше одной заявки на один проект.
*   **Управление заявками:** `TEACHER` может принимать/отклонять заявки только на свои проекты. Принятие заявки добавляет студента в `project.participants`.
*   **Поиск:** Полнотекстовый поиск по полям `title` и `description` проектов.
*   **Рекомендации:** Простой алгоритм на основе пересечения тегов в профиле студента и в проекте.

**7. ПРАВИЛА РАБОТЫ (YOUR OPERATING INSTRUCTIONS)**

*   **Инкрементальность:** Работай пошагово. Я буду давать тебе конкретные, небольшие задачи (например, "создай модель X", "напиши view для Y"). Не делай ничего сверх того, что было запрошено.
*   **Объяснения:** Кратко поясняй ключевые решения в своем коде.
*   **Чистота кода:** Следуй PEP 8. Используй осмысленные имена переменных.
*   **Зависимости:** Если добавляешь новую библиотеку, всегда указывай, что ее нужно добавить в `requirements.txt`.
*   **Безопасность:** Используй встроенные в Django средства защиты (CSRF-токены, параметризованные запросы ORM и т.д.).

------





Твоя первая задача - проанализировать проект и объяснить мне на пальцах, какие модули за что отвечают и какие файлы объясняют системе, как всё работает. Будь вкрадчивым и внимательным рассказчиком, потому что я вообще ничего не понимаю в бэкенде и хочу научиться на примере этого проекта


---

**Cursor**

Отлично! Давай разберем проект по полочкам. Я прочитаю ключевые файлы и объясню тебе, как все устроено.

Отлично! Сейчас я тебе все разложу по полочкам. Представь, что Django-приложение - это ресторан, где каждый модуль выполняет свою роль.

## 🏗️ ОБЩАЯ АРХИТЕКТУРА

**Django работает по паттерну MVT (Model-View-Template):**

- **Model (Модель)** - это база данных. Описывает, какие данные мы храним.
- **View (Представление)** - это бизнес-логика. Что делать с данными.
- **Template (Шаблон)** - это HTML-страницы. Как показать данные пользователю.

**Путь запроса пользователя:**
```
Браузер → Nginx → Gunicorn → Django (URLs → View → Model → Template) → Ответ
```

---

## 📁 СТРУКТУРА ПРОЕКТА - КТО ЗА ЧТО ОТВЕЧАЕТ

### 🔧 **Файлы конфигурации (корень проекта)**

**`docker-compose.yml`** - дирижер оркестра
- Описывает, какие "контейнеры" (изолированные программы) нужно запустить
- У нас 3 контейнера:
  - `db` - PostgreSQL база данных
  - `web` - Django-приложение
  - `nginx` - веб-сервер, который раздает статику и передает запросы Django

**`Dockerfile`** - рецепт для создания контейнера Django
- Какой Python использовать
- Какие библиотеки установить
- Как запустить приложение

**`requirements.txt`** - список библиотек Python, которые нужны проекту

---

### ⚙️ **`src/config/` - ЦЕНТРАЛЬНАЯ НЕРВНАЯ СИСТЕМА**

Это главная папка конфигурации Django. Она говорит Django, как себя вести.

**`settings.py`** - главный конфигурационный файл (самый важный!)

```python
# Подключает приложения (users, projects)
INSTALLED_APPS = [
    'apps.users',    # Приложение пользователей
    'apps.projects', # Приложение проектов
]

# Настройки базы данных (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'cusrach_db',  # имя БД
        'USER': 'cusrach_user', # пользователь
        # ...
    }
}

# Указывает, что мы используем кастомную модель User
AUTH_USER_MODEL = 'users.User'
```

**`urls.py`** - главный маршрутизатор (диспетчер)

```python
urlpatterns = [
    path('admin/', admin.site.urls),              # /admin/
    path('users/', include('apps.users.urls')),   # /users/...
    path('projects/', include('apps.projects.urls')), # /projects/...
    path('', TemplateView.as_view(...), name='home'), # Главная страница
]
```

Когда пользователь заходит на URL, Django смотрит сюда и решает, куда передать запрос.

**`manage.py`** - командная строка Django
- Это точка входа для всех команд: `python manage.py migrate`, `python manage.py runserver` и т.д.

---

### 👤 **`src/apps/users/` - ПРИЛОЖЕНИЕ ПОЛЬЗОВАТЕЛЕЙ**

Django-проект состоит из **приложений** (apps). Каждое приложение - это отдельный модуль со своей логикой.

**`models.py`** - описание данных о пользователе

```python
class User(AbstractUser):
    role = models.CharField(...)  # STUDENT или TEACHER
    bio = models.TextField(...)    # О себе
    contacts = models.CharField(...) # Контакты
    interests = models.ManyToManyField('projects.Tag') # Интересы
```

Это как таблица в Excel, где каждая строка - пользователь, а каждый столбец - поле (имя, роль, контакты и т.д.)

**`forms.py`** - формы для ввода данных

- `CustomUserCreationForm` - форма регистрации (имя, email, пароль, роль)
- `UserProfileForm` - форма редактирования профиля

**`views.py`** - бизнес-логика (что делать, когда пользователь что-то запрашивает)

- `SignUpView` - регистрация нового пользователя
- `ProfileView` - просмотр и редактирование своего профиля

**`urls.py`** - маршруты для users

```python
urlpatterns = [
    path('login/', ..., name='login'),    # /users/login/
    path('signup/', ..., name='signup'),  # /users/signup/
    path('profile/', ..., name='profile'), # /users/profile/
]
```

**`templates/users/`** - HTML-шаблоны для страниц
- `login.html` - страница входа
- `signup.html` - страница регистрации
- `profile.html` - профиль пользователя

---

### 📊 **`src/apps/projects/` - ПРИЛОЖЕНИЕ ПРОЕКТОВ**

Основная бизнес-логика платформы.

**`models.py`** - 3 главные сущности:

1. **`Tag`** - теги (например, "Machine Learning", "Web Development")
```python
class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
```

2. **`Project`** - проект
```python
class Project(models.Model):
    title = models.CharField(...)           # Название
    description = models.TextField(...)     # Описание
    creator = models.ForeignKey(User, ...)  # Создатель (преподаватель)
    status = models.CharField(...)          # RECRUITMENT, IN_PROGRESS, COMPLETED
    max_participants = models.PositiveIntegerField(...) # Мест
    application_deadline = models.DateField(...) # Дедлайн заявок
    participants = models.ManyToManyField(User, ...) # Участники
    tags = models.ManyToManyField(Tag, ...)  # Теги проекта
```

3. **`Application`** - заявка студента на проект
```python
class Application(models.Model):
    project = models.ForeignKey(Project, ...)  # На какой проект
    student = models.ForeignKey(User, ...)     # Кто подал
    status = models.CharField(...)             # PENDING, APPROVED, REJECTED
    
    class Meta:
        unique_together = ('project', 'student') # Студент может подать только 1 заявку на проект
```

**`views.py`** - куча представлений (логика для каждой страницы):

1. **Для всех:**
   - `ProjectListView` - список проектов (лента)
   - `ProjectDetailView` - детали проекта

2. **Для преподавателей:**
   - `TeacherDashboardView` - личный кабинет преподавателя (его проекты)
   - `ProjectCreateView` - создание проекта
   - `ProjectUpdateView` - редактирование проекта
   - `ManageApplicationsView` - просмотр заявок на проект
   - `ApproveApplicationView` - принять заявку
   - `RejectApplicationView` - отклонить заявку

3. **Для студентов:**
   - `ApplicationCreateView` - подать заявку на проект

**Как работает представление (View)?**

Пример `ProjectCreateView`:

```python
class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'projects/project_form.html'
    
    def test_func(self):
        return self.request.user.is_teacher  # Только преподаватель!
    
    def form_valid(self, form):
        form.instance.creator = self.request.user  # Автор = текущий пользователь
        return super().form_valid(form)
```

- `LoginRequiredMixin` - только авторизованные пользователи
- `UserPassesTestMixin` - проверка в `test_func()` (только преподаватели)
- `CreateView` - Django автоматически создает форму и сохраняет данные

**`urls.py`** - маршруты для проектов

```python
urlpatterns = [
    path('', ProjectListView.as_view(), name='project-list'),  # /projects/
    path('create/', ProjectCreateView.as_view(), ...),         # /projects/create/
    path('<int:pk>/', ProjectDetailView.as_view(), ...),       # /projects/123/
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), ...),  # /projects/123/edit/
    path('<int:project_pk>/apply/', ApplicationCreateView...), # /projects/123/apply/
]
```

`<int:pk>` - это параметр в URL (номер проекта)

**`forms.py`** - форма для создания проекта

```python
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'max_participants', ...]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'application_deadline': forms.DateInput(attrs={'type': 'date'}),
        }
```

Это описание HTML-формы на Python. Django сам генерирует HTML.

---

### 📄 **`src/templates/` - ШАБЛОНЫ (HTML)**

Django использует свой язык шаблонов:

**`base.html`** - базовый шаблон (header, footer, общая структура)
```django
<!DOCTYPE html>
<html>
<head>...</head>
<body>
    {% include 'includes/header.html' %}
    
    {% block content %}
    <!-- Здесь будет контент конкретной страницы -->
    {% endblock %}
    
    {% include 'includes/footer.html' %}
</body>
</html>
```

**`projects/project_list.html`** - наследует base.html
```django
{% extends 'base.html' %}

{% block content %}
  <h1>Список проектов</h1>
  {% for project in project_list %}
    <div>{{ project.title }}</div>
  {% endfor %}
{% endblock %}
```

Django-шаблоны используют специальный синтаксис:
- `{{ variable }}` - вывести переменную
- `{% for ... %}` - цикл
- `{% if ... %}` - условие
- `{% extends %}` / `{% block %}` - наследование шаблонов

---

## 🔄 КАК ВСЕ РАБОТАЕТ ВМЕСТЕ (ПРИМЕР)

Представь: студент хочет посмотреть список проектов.

1. **Пользователь** открывает браузер и идет на `http://localhost:8000/projects/`

2. **Nginx** (веб-сервер) получает запрос и передает его **Gunicorn** (WSGI-сервер)

3. **Gunicorn** передает запрос **Django**

4. **Django** смотрит в `config/urls.py`:
   - Видит `path('projects/', include('apps.projects.urls'))`
   - Идет в `apps/projects/urls.py`

5. В `apps/projects/urls.py` находит:
   ```python
   path('', ProjectListView.as_view(), name='project-list')
   ```

6. **ProjectListView** (в `views.py`):
   - Обращается к базе данных через модель `Project`
   - Получает список проектов (queryset)
   - Передает данные в шаблон `project_list.html`

7. **Шаблон** `project_list.html`:
   - Берет список проектов
   - Генерирует HTML (цикл `{% for project in project_list %}`)

8. Django отправляет HTML обратно в браузер

9. **Браузер** показывает красивую страницу пользователю

---

## 🗄️ БАЗА ДАННЫХ (PostgreSQL)

**Миграции** - это как версии базы данных.

Когда ты изменяешь `models.py`, нужно:

1. `python manage.py makemigrations` - создать файл миграции (описание изменений)
2. `python manage.py migrate` - применить изменения к БД

Файлы миграций хранятся в `migrations/`:
- `0001_initial.py` - первая миграция (создание таблиц)
- `0002_....py` - вторая миграция и т.д.

**ORM (Object-Relational Mapping)** - Django превращает Python-код в SQL:

```python
# Python (ORM)
projects = Project.objects.filter(status='RECRUITMENT')

# SQL (что Django делает под капотом)
SELECT * FROM projects_project WHERE status = 'RECRUITMENT';
```

---

## 🎯 КЛЮЧЕВЫЕ КОНЦЕПЦИИ

### 1. **ForeignKey** - связь "один ко многим"
```python
creator = models.ForeignKey(User, ...)
```
У проекта один создатель, но у пользователя может быть много проектов.

### 2. **ManyToManyField** - связь "многие ко многим"
```python
participants = models.ManyToManyField(User, ...)
```
У проекта может быть много участников, и у пользователя может быть много проектов.

### 3. **QuerySet** - набор объектов из БД
```python
Project.objects.all()           # Все проекты
Project.objects.filter(...)     # Фильтр
Project.objects.get(pk=1)       # Один проект с id=1
```

### 4. **Mixins** - добавляют функциональность к View
```python
class MyView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    ...
```
- `LoginRequiredMixin` - требует авторизации
- `UserPassesTestMixin` - требует прохождения теста (например, проверка роли)

---

## 📦 DOCKER - КАК ЭТО РАЗВЕРТЫВАЕТСЯ

`docker-compose up` запускает 3 контейнера:

1. **db (PostgreSQL)** - база данных на порту 5433
2. **web (Django + Gunicorn)** - приложение на порту 8000 (внутри)
3. **nginx** - веб-сервер, принимает запросы на порту 8000 (снаружи)

Контейнеры общаются между собой по сети Docker.

---

## 🎓 РЕЗЮМЕ - ЧТО ДЕЛАЕТ КАЖДЫЙ ФАЙЛ

| Файл/Папка | Роль |
|------------|------|
| `settings.py` | Главные настройки Django |
| `config/urls.py` | Главный маршрутизатор |
| `manage.py` | Командная строка Django |
| `models.py` | Описание данных (таблицы БД) |
| `views.py` | Бизнес-логика (что делать с запросом) |
| `urls.py` | Маршруты (какой URL → какой view) |
| `forms.py` | Формы для ввода данных |
| `templates/` | HTML-шаблоны |
| `static/` | CSS, JS, картинки |
| `migrations/` | Версии базы данных |
| `docker-compose.yml` | Описание контейнеров |

---

Если что-то непонятно - спрашивай! Могу углубиться в любой конкретный момент.

```plaintext
Браузер → Nginx → Gunicorn → Django (URLs → View → Model → Template) → Ответ
```

```python
# Подключает приложения (users, projects)
INSTALLED_APPS = [
    'apps.users',    # Приложение пользователей
    'apps.projects', # Приложение проектов
]

# Настройки базы данных (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'cusrach_db',  # имя БД
        'USER': 'cusrach_user', # пользователь
        # ...
    }
}

# Указывает, что мы используем кастомную модель User
AUTH_USER_MODEL = 'users.User'
```

```python
urlpatterns = [
    path('admin/', admin.site.urls),              # /admin/
    path('users/', include('apps.users.urls')),   # /users/...
    path('projects/', include('apps.projects.urls')), # /projects/...
    path('', TemplateView.as_view(...), name='home'), # Главная страница
]
```

```python
class User(AbstractUser):
    role = models.CharField(...)  # STUDENT или TEACHER
    bio = models.TextField(...)    # О себе
    contacts = models.CharField(...) # Контакты
    interests = models.ManyToManyField('projects.Tag') # Интересы
```

```python
urlpatterns = [
    path('login/', ..., name='login'),    # /users/login/
    path('signup/', ..., name='signup'),  # /users/signup/
    path('profile/', ..., name='profile'), # /users/profile/
]
```

```python
class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
```

```python
class Project(models.Model):
    title = models.CharField(...)           # Название
    description = models.TextField(...)     # Описание
    creator = models.ForeignKey(User, ...)  # Создатель (преподаватель)
    status = models.CharField(...)          # RECRUITMENT, IN_PROGRESS, COMPLETED
    max_participants = models.PositiveIntegerField(...) # Мест
    application_deadline = models.DateField(...) # Дедлайн заявок
    participants = models.ManyToManyField(User, ...) # Участники
    tags = models.ManyToManyField(Tag, ...)  # Теги проекта
```

```python
class Application(models.Model):
    project = models.ForeignKey(Project, ...)  # На какой проект
    student = models.ForeignKey(User, ...)     # Кто подал
    status = models.CharField(...)             # PENDING, APPROVED, REJECTED
    
    class Meta:
        unique_together = ('project', 'student') # Студент может подать только 1 заявку на проект
```

```python
class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'projects/project_form.html'
    
    def test_func(self):
        return self.request.user.is_teacher  # Только преподаватель!
    
    def form_valid(self, form):
        form.instance.creator = self.request.user  # Автор = текущий пользователь
        return super().form_valid(form)
```

```python
urlpatterns = [
    path('', ProjectListView.as_view(), name='project-list'),  # /projects/
    path('create/', ProjectCreateView.as_view(), ...),         # /projects/create/
    path('<int:pk>/', ProjectDetailView.as_view(), ...),       # /projects/123/
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), ...),  # /projects/123/edit/
    path('<int:project_pk>/apply/', ApplicationCreateView...), # /projects/123/apply/
]
```

```python
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'max_participants', ...]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'application_deadline': forms.DateInput(attrs={'type': 'date'}),
        }
```

```plaintext
<!DOCTYPE html>
<html>
<head>...</head>
<body>
    {% include 'includes/header.html' %}
    
    {% block content %}
    <!-- Здесь будет контент конкретной страницы -->
    {% endblock %}
    
    {% include 'includes/footer.html' %}
</body>
</html>
```

```plaintext
{% extends 'base.html' %}

{% block content %}
  <h1>Список проектов</h1>
  {% for project in project_list %}
    <div>{{ project.title }}</div>
  {% endfor %}
{% endblock %}
```

```python
   path('', ProjectListView.as_view(), name='project-list')
```

```python
# Python (ORM)
projects = Project.objects.filter(status='RECRUITMENT')

# SQL (что Django делает под капотом)
SELECT * FROM projects_project WHERE status = 'RECRUITMENT';
```

```python
creator = models.ForeignKey(User, ...)
```

```python
participants = models.ManyToManyField(User, ...)
```

```python
Project.objects.all()           # Все проекты
Project.objects.filter(...)     # Фильтр
Project.objects.get(pk=1)       # Один проект с id=1
```

```python
class MyView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    ...
```

