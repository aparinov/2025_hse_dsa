
docker-compose down -v
docker-compose up -d --build --force-recreate
docker-compose exec web python src/manage.py seed_db

docker-compose exec db psql -U user -d student_projects_db
SELECT id, username, email, role FROM users_user;
SELECT COUNT(*) FROM projects_project;

# Платформа студенческих проектов

Платформа для создания и участия в студенческих проектах университета. Проект разработан для быстрого развертывания MVP с использованием Django и Docker.

## Технологический стек

-   **Backend:** Python 3.10, Django 4.2
-   **База данных:** PostgreSQL 14
-   **Веб-сервер:** Nginx
-   **WSGI-сервер:** Gunicorn
-   **Frontend:** Django Templates, Bootstrap 5
-   **Окружение:** Docker, Docker Compose

## Локальный запуск

Для запуска проекта на локальной машине необходим установленный **Docker** и **Docker Compose**.

1.  **Клонировать репозиторий:**
    ```bash
    git clone [URL репозитория]
    cd student-projects-platform
    ```

2.  **Создать файл с переменными окружения:**
    Скопируйте файл `.env.example` в `.env`. Этот файл **не должен** попадать в Git.
    ```bash
    cp .env.example .env
    ```
    *Откройте `.env` и при необходимости измените значения (например, пароль от базы данных).*

3.  **Собрать и запустить контейнеры:**
    Эта команда скачает образы, соберет образ нашего приложения и запустит все сервисы в фоновом режиме.
    ```bash
    docker-compose up --build -d
    ```

4.  **Применить миграции базы данных:**
    После первого запуска необходимо создать таблицы в базе данных.
    ```bash
    docker-compose exec web python src/manage.py migrate
    ```

5.  **Создать суперпользователя (не нужно):**
    Для доступа к админ-панели создайте администратора.
    ```bash
    docker-compose exec web python src/manage.py createsuperuser
    ```

6.  **Готово!**
    -   Сайт доступен по адресу: `http://localhost:8000`
    -   Админ-панель: `http://localhost:8000/admin/`

## Полезные команды

-   **Остановить проект:** `docker-compose down -v`
-   **Посмотреть логи:** `docker-compose logs -f web`
-   **Выполнить команду внутри контейнера:** `docker-compose exec web [команда]` (например, `bash`)
