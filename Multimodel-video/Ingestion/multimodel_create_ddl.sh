#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : multimodel_create_ddl.sh
# Purpose     : Execute DDL statements in a .sql file against an AlloyDB
#               (PostgreSQL) instance using psql.
#
# Prerequisites:
#   - VM/host can reach AlloyDB over TCP 5432 (Private IP + firewall/peering)
#   - 'postgresql-client' available (installed below if missing)
#   - SQL file exists and DDL is idempotent (recommended for repeat runs)
# -----------------------------------------------------------------------------
#gcloud config set account "deepak.kumar214e17@cognizant.com"
#gcloud config set project "dotengage"

. ./multimodel_config.sh
# --- Configuration ---
echo $DB_PASSWORD

PASSWORD="${DB_PASSWORD}" # Password
echo $PASSWORD
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
  --file="${SQL_FILE}"

echo "DDL execution completed successfully."