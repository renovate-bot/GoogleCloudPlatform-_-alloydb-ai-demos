#!/bin/bash
# -----------------------------------------------------------------------------
# Script: medical_create_wrapper_ddl.sh
# Purpose: Execute a parameterized SQL file against an AlloyDB instance using psql.
# Usage:
. ./medical_config.sh
set -euo pipefail

# Export password for psql
export PGPASSWORD=$PASSWORD

REMOTE_ALLOYDB_IP="$1"
echo "AlloyDB Primary Instance IP: $REMOTE_ALLOYDB_IP"

if command -v psql >/dev/null 2>&1; then
  echo "psql is already installed. Skipping installation."
else
 sudo apt install postgresql-client -y
 psql --version
fi
#psql -h "${REMOTE_ALLOYDB_IP}" -p $ALLOYDB_PORT -U $USER -d $DATABASE_NAME -f $SQL_FILE

psql \
  -h "${REMOTE_ALLOYDB_IP}" \
  -p "${ALLOYDB_PORT}" \
  -U "${USER}" \
  -d "${DATABASE_NAME}" \
  --set=ON_ERROR_STOP=1 \
  --set=schema_name="${SCHEMA_NAME}" \
  --file="${PRE_SQL_FILE}"