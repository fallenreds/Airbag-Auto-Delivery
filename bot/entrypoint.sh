#!/bin/sh
#Тут выбор запуск через debugpy или обычный
if [ "$DEBUG" = "1" ]; then
  echo "[*] Debug mode enabled"
  exec python -m debugpy --listen 0.0.0.0:5678 --wait-for-client main.py
else
  echo "[*] Normal mode"
  exec python main.py
fi
