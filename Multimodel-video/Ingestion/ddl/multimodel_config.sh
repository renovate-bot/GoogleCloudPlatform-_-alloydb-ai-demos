#!/bin/bash
# --- Configuration Variables (Update these as needed) Multi Model---

#bucket creation varibles
export LOCATION="us-central1" #No need to change this
export STORAGE_CLASS="STANDARD" #No need to change this
export FOLDERS="" #Need to provide folder and sub folders for eg raw/forecast,raw/ecommexport CREATE_BUCKET="" # Need to provide bucket name which we need to create for eg alloydb-gc-usecase-test12

export PROJECT_ID=""  # Need to provide project id name here
export REGION="us-central1"  # No change required
export CLUSTER_ID="" # Need to provide name of cluster eg alloydb-dev-cluster-new
export INSTANCE_ID=""  # Need to provide Primary Instance name for eg alloydb-dev-primary-new
export DB_PASSWORD="" # Need to provide database password here.
export MACHINE_TYPE="n2-highmem-2" # No need to change here.
export NETWORK_NAME="alloydb-network"  # VPC network name No need to change here
export ACCOUNT="" # Need to provide your account id which use to connect GCP


# --------------------------- VM Configuration ---------------------------------
export INSTANCE_NAME="" # Need to provide virtual instance name here eg agent-my-vm
export ZONE_NAME="us-central1-a" # No need to change here.
export MACHINE_NAME="e2-medium" # No need to change here.
export IMAGE_FAMILY="debian-11" # OS image family no need to change here
export IMAGE_PROJECT="debian-cloud"  # OS image project no need to change here
export TAG="ssh-access" # No need to change here
export SCOPES="https://www.googleapis.com/auth/cloud-platform" # No need to change here
# --------------------------- Account / Project --------------------------------
# VPC and Subnet details (update these as per your environment) 
export VPC_NAME="default" # Target VPC network, no need to change here
export SUBNET_NAME="default"  # Target subnet within VPC, no need to change here
export ALLOYDB_PORT=5432 # No need to change here

# --- wraper Configuration ---
export DATABASE_NAME="" #Need to provide database name for eg postgres
export SQL_FILE="multimodel_create_table.sql" # SQL file to execute, no need to change here
export BUCKET="" # Need to provide Bucket path
export USER="" # Need to provide user here for eg postgres
export USERNAME="" # Need to provide username which was mentioned in home directory 
export SCHEMA_NAME="" # Need to provide schema name for eg alloydb_usecase
export SRC_MULTIMODEL="" # Provide source path where scripts present for multi_model case in cloud shell eg /home/deepak_kumar214e17/alloydb/multi_model/script/
#export SECRET_NAME="alloydb_demo_access"