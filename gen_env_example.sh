#!/bin/bash
# Генерация <path>.env.example из <path>.env: значения срезаются, ключи остаются.
#
# Прежняя версия делала `awk -F= '{print $1"="}'` по всем строкам подряд и
# поэтому портила файл: строкам-комментариям дописывался хвост "=", пустые
# строки превращались в "=", а комментарии, которых нет в .env, просто
# исчезали. Теперь комментарии и пустые строки переносятся как есть.

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Использование: $0 путь_к_env" >&2
  exit 1
fi

ENV_PATH="$1"
EXAMPLE_PATH="${ENV_PATH}.example"

if [ ! -f "$ENV_PATH" ]; then
  echo "Файл не найден: $ENV_PATH" >&2
  exit 1
fi

# ВНИМАНИЕ: .example ПЕРЕЗАПИСЫВАЕТСЯ целиком. Он ведётся руками и содержит
# пояснения, которых нет в .env, — они будут потеряны. Поэтому сначала пишем
# во временный файл и показываем разницу, а сам файл трогаем только с --force.
TMP_PATH="$(mktemp)"
trap 'rm -f "$TMP_PATH"' EXIT

awk '
  /^[[:space:]]*#/  { print; next }        # комментарий — как есть
  /^[[:space:]]*$/  { print; next }        # пустая строка — как есть
  /=/               { sub(/=.*/, "="); print; next }  # KEY=value -> KEY=
                    { print }              # всё прочее — как есть
' "$ENV_PATH" > "$TMP_PATH"

if [ ! -f "$EXAMPLE_PATH" ]; then
  cp "$TMP_PATH" "$EXAMPLE_PATH"
  echo "Создан файл $EXAMPLE_PATH"
  exit 0
fi

if diff -q "$EXAMPLE_PATH" "$TMP_PATH" >/dev/null; then
  echo "$EXAMPLE_PATH уже актуален, изменений нет"
  exit 0
fi

if [ "${2:-}" = "--force" ]; then
  cp "$TMP_PATH" "$EXAMPLE_PATH"
  echo "Перезаписан $EXAMPLE_PATH"
  exit 0
fi

echo "Разница между текущим $EXAMPLE_PATH и сгенерированным из $ENV_PATH:"
echo "  (- строки из .example, + из сгенерированного)"
echo
diff -u "$EXAMPLE_PATH" "$TMP_PATH" || true
echo
echo "Файл НЕ изменён: в .example есть пояснения, которых нет в .env, и их легко потерять."
echo "Перенесите новые ключи руками или перезапишите целиком: $0 $ENV_PATH --force"
