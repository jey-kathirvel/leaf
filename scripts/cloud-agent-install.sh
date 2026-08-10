#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./scripts/cloud-agent-postgres.sh

cat > .env <<EOF
APP_NAME=Leaf Online Store
APP_ENV=development
DEBUG=true
BASE_URL=http://127.0.0.1:8070
HOST=127.0.0.1
PORT=8070
DATABASE_URL=postgresql+psycopg2://leaf_store_user:leaf_store_dev_pass@127.0.0.1:5432/leaf_store_db
SECRET_KEY=dev-secret-key-not-for-production
SESSION_SECRET_KEY=dev-session-secret-not-for-production
SESSION_COOKIE_NAME=leaf_admin_session
SESSION_MAX_AGE=28800
UPLOAD_DIR=${ROOT}/app/uploads
MAX_UPLOAD_SIZE_MB=10
UPI_ENABLED=false
UPI_VPA=merchant@bank
UPI_PAYEE_NAME=Leaf Online Store
EOF

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

mkdir -p app/uploads

.venv/bin/python -m alembic upgrade head
PYTHONPATH="$ROOT" .venv/bin/python scripts/cloud-agent-seed.py
