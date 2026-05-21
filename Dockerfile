# Этап 1: Базовый образ
FROM python:3.10-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем рабочую директорию
WORKDIR /app

# Установка зависимостей
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2+cpu && \
    pip install -r requirements.txt

# Создаем пользователя без прав root для безопасности
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Копируем исходный код
COPY ./src /app/src
COPY ./.docker/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Меняем владельца файлов на нашего пользователя
RUN chown -R appuser:appgroup /app

# Переключаемся на пользователя без прав root
USER appuser

# Запускаем entrypoint скрипт, который будет выполнять команды Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--chdir", "src", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
