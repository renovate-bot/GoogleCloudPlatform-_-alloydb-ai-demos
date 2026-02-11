#!/bin/bash
# Purpose:
#   - Create (or skip if exists) an AlloyDB cluster
#   - Create a PRIMARY AlloyDB instance for the cluster
#   - Call a .sh script to execute DDL against the AlloyDB database

#. "$MEDICAL_CONFIG"
#. /home/deepak_kumar214e17/alloydb/medical/script/medical_config.param
source ./medical_config.sh
echo $PROJECT_ID
echo $REGION
echo $CLUSTER_ID

gcloud config set account ${ACCOUNT}

# --- Authenticate and Set Project ---
echo "Authenticating to Google Cloud..."
#gcloud auth login --no-launch-browser # Use --no-launch-browser for scripting
gcloud config set project "${PROJECT_ID}"


# --- Create AlloyDB Cluster ---
# Check if cluster exists
if gcloud alloydb clusters describe "$CLUSTER_ID" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
 echo "Cluster '$CLUSTER_ID' already exists. Skipping creation."
else 
 echo "Creating AlloyDB cluster: ${CLUSTER_ID} in ${REGION}..."
 gcloud alloydb clusters create "${CLUSTER_ID}" \
     --region="${REGION}" \
     --network="projects/${PROJECT_ID}/global/networks/default" \
     --password="${DB_PASSWORD}" \
     --database-version=POSTGRES_14
fi
if gcloud alloydb instances describe "$INSTANCE_ID" --cluster="$CLUSTER_ID" --region="$REGION" --format="value(name)" >/dev/null 2>&1; then
  echo "AlloyDB instance '$INSTANCE_ID' already exists in cluster '$CLUSTER_ID' (region $REGION). Skipping creation."
else
 # --- Create Primary Instance ---
 echo "Creating primary instance: ${INSTANCE_ID} in cluster ${CLUSTER_ID}..."
 gcloud alloydb instances create "${INSTANCE_ID}" \
     --cluster="${CLUSTER_ID}" \
     --region="${REGION}" \
     --instance-type=PRIMARY \
     --machine-type="${MACHINE_TYPE}" \
     --database-flags="alloydb_ai_nl.enabled=on,alloydb.iam_authentication=on,google_ml_integration.enable_model_support=on,password.enforce_complexity=on" \
     --availability-type=REGIONAL # Use REGIONAL for HA, ZONAL for basic instance
fi
if [ $? -eq 0 ]; then
    echo "AlloyDB primary instance '${INSTANCE_ID}' created successfully."
else
    echo "Error creating primary instance '${INSTANCE_ID}'. Exiting."
    exit 1
fi

echo "AlloyDB cluster and primary instance creation script completed."