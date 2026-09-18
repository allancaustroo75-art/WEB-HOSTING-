#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "🚀 SNUKED HOSTER - Premium Telegram Mini App Hosting"
echo "================================================"

if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python -m venv .venv
fi

echo "📥 Installing dependencies..."
. .venv/bin/activate
pip install -q -r backend/requirements.txt

export PYTHONPATH=.

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo ""
echo "🔧 Configuration: backend/config.py (no .env required)"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo "   Config file: backend/config.py"
echo "   Edit BOT_TOKEN, OWNER_USER_ID, SECRET_KEY in backend/config.py"
echo ""

# Optional .env check - no longer required
if [ -f ".env" ]; then
  echo "ℹ️  Found .env file - values will be loaded as env vars (optional, overrides config.py)"
else
  echo "✅ Using backend/config.py for configuration (no .env needed)"
fi

echo "🌐 Starting SNUKED HOSTER server..."
echo "   Health check: http://$HOST:$PORT/health"
echo "   Mini App: http://$HOST:$PORT/"
echo "   API Docs: http://$HOST:$PORT/docs"
echo ""

exec uvicorn backend.app:app --host "$HOST" --port "$PORT" --log-level info
