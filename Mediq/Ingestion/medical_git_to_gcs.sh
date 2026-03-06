#!/bin/bash
# Purpose:
#   - Pull latest data files from a Git repo working directory
#   - Preprocess the target CSV (remove header)
#   - Upload the processed file to a Google Cloud Storage (GCS) bucket
#
# Assumptions:
#   - Paths and variables are defined in medical_config.param:
#       HOMEDIR, CLONE_DIR, CLONE_DIR_MED, FILES_TO_UPLOAD, BUCKET_NAME
#   - This host has git and gsutil installed and authenticated
source ./medical_config.sh
gcloud config set account "${ACCOUNT}"
gcloud config set project "${PROJECT_ID}"


# Variables

# Clone the repo
echo "copying the file from gitrepo to gcs bucket"
#git clone "$REPO_URL" "$CLONE_DIR"

# Expand wildcard into array
# Set permissions

echo "directory checking block started"
if [ -d "$HOMEDIR/$CLONE_DIR" ]; then
        echo "Directory exist, pulling latest changes"
        cd "$HOMEDIR/$CLONE_DIR"
        git pull --no-rebase
        sleep 5
else 
        echo "cloning directory"
        git clone "$REPO_URL" "$CLONE_DIR"
fi


cd "${CLONE_DIR_MED}"
#FILES_TO_UPLOAD=(*ecommerce*)
#echo "${FILES_TO_UPLOAD[@]}"

FILES_TO_UPLOAD="${FILES_TO_UPLOAD}"
echo "${FILES_TO_UPLOAD}"

#chmod 777 "$HOMEDIR/$CLONE_DIR/${FILES_TO_UPLOAD[@]}"
#chmod 777 "${FILES_TO_UPLOAD[@]}"

chmod 777 "${FILES_TO_UPLOAD}"
wc -l "${FILES_TO_UPLOAD}"
sed '1d' "$FILES_TO_UPLOAD" > tmp_med.csv
wc -l tmp_med.csv
mv tmp_med.csv "$FILES_TO_UPLOAD"
chmod 777 "${FILES_TO_UPLOAD}"
wc -l "${FILES_TO_UPLOAD}"


#sed '1d' "${FILE_NAME}" > "${FILE_NAME}"
#chmod 777 "${FILE_NAME}"

# Upload to GCS

gsutil -m cp "${FILES_TO_UPLOAD}" "$BUCKET_NAME"

# Upload to GCS
#gsutil -m cp -r "$HOMEDIR/$CLONE_DIR/$FOLDER_TO_UPLOAD" "$BUCKET_NAME"

if [ $? -eq 0 ]; then
    echo "File moved to GCS bucket successfully."
else
    echo "Error file not moved to GCS location. hence exiting."
    exit 1
fi
