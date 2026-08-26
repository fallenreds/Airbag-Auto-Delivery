#!/bin/sh
# Старт backend: сначала привести базу и статику в рабочее состояние, потом
# принимать запросы.
#
# Раньше Dockerfile запускал gunicorn напрямую, а миграции накатывались руками.
# 17.08.2026 про них забыли, и оформление заказов лежало двое суток: каждый
# POST падал на `no such column: core_order.cancel_state`. Двадцать неудачных
# попыток клиентов — и ни одного сигнала, потому что снаружи это выглядело как
# обычная 500.
set -eu

echo "[entrypoint] applying migrations"
python manage.py migrate --noinput

echo "[entrypoint] collecting static"
python manage.py collectstatic --noinput

echo "[entrypoint] starting: $*"
exec "$@"
