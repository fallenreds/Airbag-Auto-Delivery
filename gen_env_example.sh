#!/bin/bash
# Скрипт для генерации env.example из указанного .env

if [ -z "$1" ]; then
  echo "Использование: $0 путь_к_env"
  exit 1
fi

ENV_PATH="$1"
EXAMPLE_PATH="${ENV_PATH}.example"

awk -F= '{print $1"="}' "$ENV_PATH" > "$EXAMPLE_PATH"
echo "Создан файл $EXAMPLE_PATH"
