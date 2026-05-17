#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=== Starting docker compose (build if needed) ==="
docker compose up -d --build

echo ""
echo "=== Starting ngrok tunnels (fallenreds + frontend) ==="
pkill -f "ngrok start" 2>/dev/null || true
sleep 1
ngrok start fallenreds frontend > /dev/null 2>&1 &
NGROK_PID=$!
echo "ngrok PID: $NGROK_PID"

echo "Waiting for ngrok to start..."
sleep 5

echo ""
echo "=== Getting tunnel URLs from ngrok API ==="
NGROK_JSON=$(curl -s http://localhost:4040/api/tunnels)

FRONTEND_URL=$(echo "$NGROK_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('tunnels', []):
    addr = t.get('config', {}).get('addr', '')
    if ':3000' in addr and t.get('public_url', '').startswith('https'):
        print(t['public_url'])
        break
" 2>/dev/null)

BACKEND_URL="https://minimally-consensual-aurore.ngrok-free.dev"

if [ -z "$FRONTEND_URL" ]; then
    echo "ERROR: Could not get frontend URL from ngrok API"
    echo "Check http://localhost:4040 in your browser"
    exit 1
fi

echo "Frontend URL : $FRONTEND_URL"
echo "Backend URL  : $BACKEND_URL"

echo ""
echo "=== Updating bot/.env WEB_APP_URL ==="
sed -i "s|WEB_APP_URL=.*|WEB_APP_URL=\"$FRONTEND_URL\"|" bot/.env
echo "Updated bot/.env -> WEB_APP_URL=\"$FRONTEND_URL\""

echo ""
echo "=== Restarting bot container ==="
docker compose restart bot

echo ""
echo "==================================================================="
echo "  All done!"
echo "  Frontend (Mini App) : $FRONTEND_URL"
echo "  Backend API         : $BACKEND_URL/api/v2/"
echo "  ngrok Inspector     : http://localhost:4040"
echo "  Telegram: send /start to your bot to see the shop button"
echo "==================================================================="
