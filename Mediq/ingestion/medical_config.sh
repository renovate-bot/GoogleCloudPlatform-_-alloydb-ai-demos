#!/bin/bash
# --- Configuration Variables ---
export MEDICAL_CONFIG="/home/deepak_kumar214e17/alloydb/medical/script/medical_config.param"
export PROJECT_ID="dotengage"
export REGION="us-central1"
export CLUSTER_ID="alloydb-dev-cluster-new"
export INSTANCE_ID="alloydb-dev-primary-new"
export DB_PASSWORD="AlloyDB_Dev"
export MACHINE_TYPE="n2-highmem-2" # Example machine type
export NETWORK_NAME="alloydb-network"
export ACCOUNT="deepak.kumar214e17@cognizant.com"

# git Variables
export REPO_URL="https://github.com/deepakbhalia1920/srcdump.git"
export CLONE_DIR="raw_dataset"
export CLONE_DIR_MED="/home/deepak_kumar214e17/raw_dataset/Medical/dataset"
export BUCKET_NAME="gs://alloydb-gc-usecase-newsetup/raw/medical/"
#FOLDER_TO_UPLOAD="load_data*.sh"  # relative path inside repo
export HOMEDIR="/home/deepak_kumar214e17"
export FILES_TO_UPLOAD="disease_medtests.csv"

# Updated script to create VM, ensure AlloyDB connectivity, and run DDL

export INSTANCE_NAME="agent-my-vm-test16"
export ZONE_NAME="us-central1-a"
export MACHINE_NAME="e2-medium"
export IMAGE_FAMILY="debian-11"
export IMAGE_PROJECT="debian-cloud"
export TAG="ssh-access"
export SCOPES="https://www.googleapis.com/auth/cloud-platform"

# VPC and Subnet details (update these as per your environment)
export VPC_NAME="default"
export SUBNET_NAME="default"
export ALLOYDB_PORT=5432

# --- wrapper Configuration ---
export DATABASE_NAME="postgres"
export SQL_FILE="medical_create_table.sql"
export BUCKET="gs://alloydb-usecase/uploads"
export USER="postgres"
export PASSWORD="AlloyDB_Dev"
export PRE_SQL_FILE="medical_presql.sql"


################################
export BUCKET_NAME_ROOT="alloydb-gc-usecase-newsetup"
#MED_TABLE="alloydb_demo.disease_tests_info_1401"
export SCHEMA_NAME="alloydb_usecase"

export USERNAME="deepak_kumar214e17"