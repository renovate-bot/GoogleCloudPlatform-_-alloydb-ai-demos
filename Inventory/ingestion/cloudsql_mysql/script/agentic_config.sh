#!/bin/bash
# --------------------------- Configuration -----------------------------------

#bucket creation varibles
export LOCATION="us-central1" #No need to change here
export STORAGE_CLASS="STANDARD" #No need to change here
export FOLDERS="" #Need to provide folder/sub-folder for gcp location for eg raw/forecast,raw/ecomm
export CREATE_BUCKET="" # Need to provide bucket name for eg alloydb-gc-usecase

export PROJECT_ID="" # Need to provide GCP Project ID
export INSTANCE_NAME="" # Need to provide Cloud MySQL instance name for eg cloudsql-mysql-instance-vertexai
export REGION="us-central1" # No need to change here, Region for the instance
export TIER="db-n1-standard-1"            # No need to change here, choose a tier to match workload
export EDITION="ENTERPRISE" #No need to change here
export ROOT_PASSWORD="" # Need to provide initial root password
export DATABASE_VERSION="MYSQL_8_0_36" #No need to change here

# --- Configuration ---
export HOST="127.0.0.1" # No need to change here Proxy binds locally; MySQL client connects to localhost

# If you prefer Private IP only, set PRIVATE_ONLY=true and provide VPC self-link
PRIVATE_ONLY=false #No need to change here
VPC_SELF_LINK=""  # e.g. "projects/${PROJECT_ID}/global/networks/default"
ACCOUNT="" #Need to provide gcp account mail id

export DB_NAME="" #Need to provide database name for eg mysql
export APP_DB_NAME="" #Need to provide schema name
export SQL_FILE="agentic_mysql_create_table.sql" # No need to change here, DDL file that creates tables etc.
export DB_USER="root" # No need to change here, Admin (or privileged) MySQL user
export PASSWORD="" # Need to provide Admin password

# --- New User Details ---
export NEW_USER="" #Need to provide new username for eg app_user
export NEW_PASSWORD="" # Need to provide password for new user Choose a strong, secure password for the new user
export NEW_USER_DB_NAME="" # Need to provide schema name , The database this new user will primarily access