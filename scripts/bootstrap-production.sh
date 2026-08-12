#!/usr/bin/env bash
set -euo pipefail

# One-time (or repair) production bootstrap for /opt/leaf-store on the VPS.
# Run on the server as root:
#   cd /opt/leaf-store && bash scripts/bootstrap-production.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICE_USER="${LEAF_SERVICE_USER:-leaf}"
SERVICE_GROUP="${LEAF_SERVICE_GROUP:-www-data}"

if ! id "$SERVICE_USER" &>/dev/null; then
  echo "Service user '$SERVICE_USER' does not exist. Create it or set LEAF_SERVICE_USER." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it (for example: apt install python3 python3-venv)." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating .venv ..."
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

echo "Bootstrap complete. Run migrations as the service user:"
echo "  sudo -u $SERVICE_USER $ROOT/.venv/bin/python -m alembic upgrade head"
echo "Then restart:"
echo "  sudo systemctl restart leaf-store.service"
