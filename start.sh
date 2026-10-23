#!/bin/bash
# Запуск локального сервера Device Studio для установки на подключенный по USB iPhone
cd "$(dirname "$0")"

PORT=5050
echo "======================================================="
echo "🍏 Запуск IPA Studio (Device Studio) на http://localhost:$PORT..."
echo "📱 Подключите iPhone кабелем USB к этому компьютеру"
echo "🌐 Откройте в браузере: http://localhost:$PORT"
echo "======================================================="

# Открываем в браузере на macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    (sleep 1 && open "http://localhost:$PORT") &
fi

python3 server.py $PORT
