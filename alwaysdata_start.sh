#!/bin/bash
# ==============================================================================
# Klinika Navbat Tizimi — Alwaysdata.com Ishga tushirish skripti
# ==============================================================================
set -e

# Joriy loyiha katalogiga o'tish
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏥 Klinika tizimi ishga tushirilmoqda..."

# 1. Virtual environment mavjudligini tekshirish
if [ ! -d "venv" ]; then
    echo "📦 Yangi virtualenv (venv) yaratilmoqda..."
    python3 -m venv venv
    venv/bin/pip install --upgrade pip
    venv/bin/pip install -r requirements.txt
fi

# 2. .env fayli mavjudligini tekshirish
if [ ! -f ".env" ]; then
    echo "⚠️ .env fayli topilmadi! .env.production.example dan nusxa olinmoqda..."
    cp .env.production.example .env
    echo "❗ ILTIMOS: .env faylini ochib, BOT_TOKEN, SUPER_ADMIN_PASSWORD va SECRET_KEY ni sozlang!"
fi

# 3. Papkalarni yaratish
mkdir -p data backups logs

# 4. Port va Host sozlamalari (Alwaysdata $PORT yoki $ALWAYSDATA_HTTPD_PORT beradi)
PORT="${PORT:-${ALWAYSDATA_HTTPD_PORT:-8000}}"
HOST="::"

echo "🚀 Uvicorn serveri ishga tushmoqda: Host=$HOST, Port=$PORT"

# 5. Uvicorn orqali FastAPI ilovasini ishga tushirish
exec venv/bin/uvicorn main:app --host "$HOST" --port "$PORT" --workers 1
