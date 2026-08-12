#!/usr/bin/env bash
# Run on the Hostinger VPS as root (single copy-paste deploy).
#   cd /opt/leaf-store && bash scripts/deploy-on-server.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICE_USER="${LEAF_SERVICE_USER:-leaf}"
SERVICE_GROUP="${LEAF_SERVICE_GROUP:-www-data}"
BRANCH="${LEAF_DEPLOY_BRANCH:-main}"

echo "==> Leaf deploy in $ROOT (branch $BRANCH)"

if ! command -v python3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-venv python3-dev libpq-dev build-essential git
fi

if ! id "$SERVICE_USER" &>/dev/null; then
  echo "==> Creating system user $SERVICE_USER"
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  SERVICE_GROUP="$SERVICE_USER"
fi

echo "==> Git pull"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "==> Python venv + dependencies"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

mkdir -p app/uploads
chown -R "$SERVICE_USER:$SERVICE_GROUP" .venv app/uploads
if [[ -f .env ]]; then
  chown "$SERVICE_USER:$SERVICE_GROUP" .env
  chmod 640 .env
fi

echo "==> Database migrations"
.venv/bin/python -m alembic upgrade head

if systemctl list-unit-files | grep -q '^leaf-store.service'; then
  echo "==> Restart leaf-store.service"
  systemctl restart leaf-store.service
  systemctl is-active leaf-store.service
  curl -fsS http://127.0.0.1:8070/health || true
else
  echo "WARN: leaf-store.service not installed. Copy deploy/leaf-store.service to systemd and enable it."
fi

echo "==> Deploy complete."
