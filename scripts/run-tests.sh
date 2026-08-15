#!/usr/bin/env bash
# Полный прогон тестов проекта: backend (Django), bot (pytest), frontend (vitest).
#
# Используется вручную и из pre-commit хука. Каждый блок пропускается, если
# соответствующее окружение не поднято, — но если окружение есть, падение теста
# валит весь скрипт.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=0

run() {
    local name="$1"
    shift
    echo ""
    echo "=== ${name} ==="
    if ! "$@"; then
        echo "✗ ${name} FAILED"
        FAILED=1
    fi
}

# --- backend ---------------------------------------------------------------
BACKEND_PY="${ROOT}/backend/.venv/bin/python"
[ -x "${BACKEND_PY}" ] || BACKEND_PY="$(command -v python3 || true)"

if [ -n "${BACKEND_PY}" ] && [ -f "${ROOT}/backend/manage.py" ]; then
    run "backend" env -C "${ROOT}/backend" "${BACKEND_PY}" manage.py test payments core.tests
else
    echo "— backend: python не найден, пропуск"
fi

# --- bot -------------------------------------------------------------------
# Берём первый интерпретатор, в котором реально стоит pytest: в bot/venv его
# может не быть (bot/requirements-test.txt ставится отдельно).
BOT_PY=""
for candidate in "${ROOT}/bot/venv/bin/python" "${BACKEND_PY}" "$(command -v python3 || true)"; do
    if [ -n "${candidate}" ] && [ -x "${candidate}" ] && \
       "${candidate}" -c "import pytest" >/dev/null 2>&1; then
        BOT_PY="${candidate}"
        break
    fi
done

if [ -n "${BOT_PY}" ]; then
    run "bot" env -C "${ROOT}/bot" "${BOT_PY}" -m pytest -q
else
    echo "— bot: pytest не установлен (pip install -r bot/requirements-test.txt), пропуск"
fi

# --- frontend --------------------------------------------------------------
if [ -d "${ROOT}/frontend/node_modules/vitest" ]; then
    run "frontend" env -C "${ROOT}/frontend" npm test --silent
else
    echo "— frontend: node_modules не установлены, пропуск"
fi

echo ""
if [ "${FAILED}" -ne 0 ]; then
    echo "✗ Есть падающие тесты"
    exit 1
fi
echo "✓ Все прогнанные наборы зелёные"
