#!/bin/sh
# Runs ONCE, the first time the database volume is created (never on later starts).
# Mirrors the local setup: an admin owns the database, the app uses a limited role.
set -e

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
     -v admin_user="$POSTGRES_USER" \
     -v app_user="$APP_DB_USER" -v app_pass="$APP_DB_PASSWORD" -v app_db="$APP_DB_NAME" <<'SQL'
-- :"x" quotes a value as an identifier, :'x' as a string literal (safe against odd characters).
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_pass';
CREATE DATABASE :"app_db" OWNER :"admin_user";
\connect :"app_db"
GRANT CONNECT ON DATABASE :"app_db" TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL
