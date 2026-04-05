#!/bin/sh

# Выходим, если любая команда завершится с ошибкой
set -e

echo "Waiting for PostgreSQL to start..."
# nc (netcat) не всегда есть в slim образах, используем более надежный метод
# Вместо этого, healthcheck в docker-compose уже гарантирует доступность DB

echo "Applying database migrations..."
python src/manage.py migrate --noinput

echo "Collecting static files..."
python src/manage.py collectstatic --noinput --clear

# Запускаем основной процесс контейнера (переданный через CMD)
exec "$@"
