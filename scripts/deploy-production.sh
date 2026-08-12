#!/usr/bin/env bash
set -euo pipefail

# Deploy Leaf to a Hostinger VPS (default path /opt/leaf-store).
#
# Usage (from your machine with SSH access to the server):
#   export LEAF_DEPLOY_HOST="user@your-server-hostname"
#   export LEAF_DEPLOY_PATH="/opt/leaf-store"
#   ./scripts/deploy-production.sh
#
# Optional:
#   LEAF_DEPLOY_BRANCH=main
#   LEAF_DEPLOY_SERVICE=leaf-store.service

HOST="${LEAF_DEPLOY_HOST:-}"
PATH_ON_SERVER="${LEAF_DEPLOY_PATH:-/opt/leaf-store}"
BRANCH="${LEAF_DEPLOY_BRANCH:-main}"
SERVICE="${LEAF_DEPLOY_SERVICE:-leaf-store.service}"

if [[ -z "$HOST" ]]; then
  echo "Set LEAF_DEPLOY_HOST (for example user@leaf.ads-ai.in) and rerun." >&2
  exit 1
fi

ssh "$HOST" bash -s <<EOF
set -euo pipefail
cd "$PATH_ON_SERVER"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull origin "$BRANCH"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest tests/ -q
sudo systemctl restart "$SERVICE"
sudo systemctl is-active "$SERVICE"
curl -fsS http://127.0.0.1:8070/health
EOF

echo "Deploy finished for $HOST ($PATH_ON_SERVER)."
