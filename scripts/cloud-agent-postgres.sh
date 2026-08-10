#!/usr/bin/env bash
set -euo pipefail

DB_USER="${LEAF_DB_USER:-leaf_store_user}"
DB_PASS="${LEAF_DB_PASS:-leaf_store_dev_pass}"
DB_NAME="${LEAF_DB_NAME:-leaf_store_db}"

if ! command -v pg_isready >/dev/null 2>&1; then
  echo "PostgreSQL client tools are not installed." >&2
  exit 1
fi

if ! pg_isready -q 2>/dev/null; then
  sudo service postgresql start
  for _ in $(seq 1 30); do
    if pg_isready -q 2>/dev/null; then
      break
    fi
    sleep 1
  done
fi

if ! pg_isready -q; then
  echo "PostgreSQL failed to become ready." >&2
  exit 1
fi

role_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" || true)"
if [[ "${role_exists}" != "1" ]]; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
fi

db_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" || true)"
if [[ "${db_exists}" != "1" ]]; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
  "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"
