#!/usr/bin/env bash
set -euo pipefail

# One-time (or repair) production bootstrap for /opt/leaf-store on the VPS.
# Run on the server as root:
#   cd /opt/leaf-store && bash scripts/bootstrap-production.sh
#
# Optional:
#   LEAF_CREATE_SERVICE_USER=1   create system user "leaf" if missing
#   LEAF_SERVICE_USER=www-data   use a different runtime user

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICE_USER="${LEAF_SERVICE_USER:-}"
SERVICE_GROUP="${LEAF_SERVICE_GROUP:-www-data}"

if [[ -z "$SERVICE_USER" ]]; then
  UNIT="/etc/systemd/system/leaf-store.service"
  if [[ -f "$UNIT" ]]; then
    SERVICE_USER="$(grep -E '^User=' "$UNIT" | head -1 | cut -d= -f2)"
  fi
  SERVICE_USER="${SERVICE_USER:-leaf}"
fi

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  SERVICE_GROUP="${SERVICE_USER}"
fi

if ! id "$SERVICE_USER" &>/dev/null; then
  if [[ "${LEAF_CREATE_SERVICE_USER:-}" == "1" ]]; then
    echo "Creating system user '$SERVICE_USER' ..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  else
    echo "Service user '$SERVICE_USER' does not exist." >&2
    echo "Create it, then rerun:" >&2
    echo "  useradd --system --no-create-home --shell /usr/sbin/nologin $SERVICE_USER" >&2
    echo "Or rerun with: LEAF_CREATE_SERVICE_USER=1 bash scripts/bootstrap-production.sh" >&2
  exit 1
  fi
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

echo "Bootstrap complete."
echo "Run migrations (as root or as $SERVICE_USER):"
echo "  $ROOT/.venv/bin/python -m alembic upgrade head"
echo "Then restart:"
echo "  systemctl restart leaf-store.service"
