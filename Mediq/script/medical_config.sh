#!/bin/bash
# --- Configuration Variables ---Medical usecase

#bucket creation varibles
export LOCATION="us-central1" #No need to change this
export STORAGE_CLASS="STANDARD" #No need to change this
export FOLDERS="" #Need to provide folder and sub folders for eg raw/forecast,raw/ecommexport CREATE_BUCKET="" # Need to provide bucket name which we need to create for eg alloydb-gc-usecase-test12

export PROJECT_ID=""  #Need to provide project id name here
export REGION="us-central1" # No change required
export CLUSTER_ID="" # Need to provide name of cluster eg alloydb-dev-cluster-new
export INSTANCE_ID="" # Need to provide Primary Instance name for eg alloydb-dev-primary-new
export DB_PASSWORD="" # Need to provide database password here.
export MACHINE_TYPE="n2-highmem-2" # No need to change here.
export NETWORK_NAME="alloydb-network" # No need to change here.
export ACCOUNT="" # Need to provide your account id which use to connect GCP

# git Variables
export REPO_URL="" # Need to provide Git repo link here eg https://github.com/deepakbhalia1920/srcdump.git
export CLONE_DIR="raw_dataset"
export CLONE_DIR_MED="/home/deepak_kumar214e17/raw_dataset/Medical/dataset"
export BUCKET_NAME="" # Need to provide bucket path here eg gs://alloydb-gc-usecase-newsetup/raw/medical/
export HOMEDIR="" # Need to provide your home directory path eg /home/deepak_kumar214e17
export FILES_TO_UPLOAD="disease_tests_info.csv" #File name must be like this only

# Updated script to create VM, ensure AlloyDB connectivity, and run DDL

export INSTANCE_NAME="" # Need to provide virtual instance name here eg agent-my-vm
export ZONE_NAME="us-central1-a" # No need to change here.
export MACHINE_NAME="e2-medium" # No need to change here.
export IMAGE_FAMILY="debian-11" # No need to change here.
export IMAGE_PROJECT="debian-cloud" # No need to change here.
export TAG="ssh-access" # No need to change here.
export SCOPES="https://www.googleapis.com/auth/cloud-platform" # No need to change here.

# VPC and Subnet details (update these as per your environment)
export VPC_NAME="default" # No need to change here.
export SUBNET_NAME="default" # No need to change here.
export ALLOYDB_PORT=5432 # No need to change here.

# --- wrapper Configuration ---
export DATABASE_NAME="" #Need to provide database name for eg postgres
export SQL_FILE="medical_create_table.sql" # No need to change here
export BUCKET="" # Need to provide Bucket path
export USER="" # Need to provide user here for eg postgres
export PASSWORD="" # Need to mention here password which user need to access database.
export PRE_SQL_FILE="medical_create_presql.sql" # No need to change here


################################
export BUCKET_NAME_ROOT="" # Need to provide bucket root path for eg alloydb-gc-usecase-newsetup
#MED_TABLE="alloydb_demo.disease_tests_info_1401"
export SCHEMA_NAME="" # Need to provide schema name for eg alloydb_usecase

export USERNAME="" # Need to provide username which was mentioned in home directory 

export SRC_MED="" # Provide source path where scripts present for medical use case in cloud shell eg /home/deepak_kumar214e17/alloydb/medical/script/
