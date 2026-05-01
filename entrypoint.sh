#!/bin/bash
set -e

python manage.py migrate --no-input

if [ "${DJANGO_SETTINGS_MODULE}" = "config.settings.production" ]; then
    python manage.py collectstatic --no-input --clear
fi

exec "$@"
