#!/bin/sh
set -eu

envsubst '${PORT}' \
    < /etc/nginx/templates/securedesk.conf.template \
    > /etc/nginx/conf.d/default.conf

alembic upgrade head
python scripts/bootstrap_admin.py

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!

shutdown() {
    kill -TERM "$api_pid" 2>/dev/null || true
}
trap shutdown INT TERM EXIT

nginx -g 'daemon off;'
