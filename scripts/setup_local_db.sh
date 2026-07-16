#!/usr/bin/env bash
# Bootstrap a local Postgres database for PolyCrawler development.
# Requires: PostgreSQL 14+ installed and running.
set -euo pipefail

DB_USER="${POLY_DB_USER:-polycrawler}"
DB_PASS="${POLY_DB_PASS:-polycrawler}"
DB_NAME="${POLY_DB_NAME:-poly_crawler}"
DB_HOST="${POLY_DB_HOST:-localhost}"
DB_PORT="${POLY_DB_PORT:-5432}"

echo "Creating role/database if missing (user=${DB_USER}, db=${DB_NAME})..."

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}' SUPERUSER;
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

export POLY_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "POLY_DATABASE_URL=${POLY_DATABASE_URL}"
echo "Running alembic upgrade head..."
alembic upgrade head
echo "Validating schema..."
python3 scripts/validate_schema.py
echo "Local DB ready."
