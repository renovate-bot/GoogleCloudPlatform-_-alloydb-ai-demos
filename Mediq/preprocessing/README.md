# AlloyDB Healthcare Usecase: MedIQ Demo application

Demo application built using AlloyDB for Healthcare domain using **unstructured PDFs** and **structured CSV** (MIMIC-IV demo) sources. It extracts disease-related text chunks and images, writes them to CSV, and ingests them into AlloyDB with embeddings (via `google_ml.embedding`).

---
## Features
- Config-driven AlloyDB connectivity via the AlloyDB Connector and SQLAlchemy.
- PDF parsing & heading detection, with per-page chunking using LangChain splitters.
- Disease-name extraction via Vertex AI Gemini (optional helper class).
- CSV utilities to read/write chunks and unmatched items.
- DDL helpers to ensure extensions, tables, merge 3 tables into 1, and build a ScaNN index (optional).
- Image extraction from PDFs, saved to disk and/or Base64 for DB.
- Reusable CLI scripts for end-to-end flows.

> This repo intentionally **does not store secrets**. Use environment variables or `.env` (not committed) to configure credentials.


---
## Quickstart

1. **Python environment**

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


2. **Configure environment variables** :

- Create a .env file with necessary configurations

3. **Authenticate to GCP**

- Ensure `GOOGLE_APPLICATION_CREDENTIALS` points to a service account JSON with access to AlloyDB & Vertex AI.

4. **Create disease_tests_info.csv file from Kaggle** : https://www.kaggle.com/datasets/montassarba/mimic-iv-clinical-database-demo-2-2/data 

python -m scripts.pull_kaggle_demo \
  --dataset-url https://www.kaggle.com/datasets/montassarba/mimic-iv-clinical-database-demo-2-2/croissant/download \
  --files d_labitems.csv labevents.csv d_icd_diagnoses.csv diagnoses_icd.csv \
  --out-dir data/kaggle_mimic_demo \
  --build-tests-info \
  --tests-info-out disease_tests_info.csv

5. **Run PDF + CSV preprocessing**

python -m scripts.preprocess_text \
  --pdf <PATH TO The-Gale-Encyclopedia-of-Medicine-3rd-Edition.pdf> \
  --csv disease_tests_info.csv \
  --out-chunks outputs/extract_pdf_chunks.csv \
  --out-unmatched outputs/unmatched_diseases.csv \
  --use-vertex-matcher --vertex-project-id <PROJECT_ID> \
  --index-page-start 9 --index-page-end 21 \
  --filter-original-in-place \
  --log-level INFO

disease_tests_info.csv created from this step is to be ingested into AlloyDB (see ingestion folder)

6. **Load chunks into AlloyDB**

python -m scripts.ingest_chunks_to_alloydb \
  --chunks outputs/extract_pdf_chunks.csv \
  --schema <SCHEMA_NAME> \
  --table disease_details_info

7. (A) **Extract images (Optional)** : Only if images are to be shown along with response
Pre-requisite: disease_images_final.pdf prepared (images + captions) from images in Encyclopedia from the list of common diseases. This can be prepared manually by copying images with captions from Encyclopedia PDF for the common diseases. Replace disease_images_final_sample with your PDF. 

python -m scripts.extract_images \
  --pdf <PATH TO disease_images_final.pdf> \
  --out-dir extracted_data \
  --out-csv outputs/disease_images_info.csv

(B) **Ingest images to AlloyDB (after step A)** 

python -m scripts.ingest_images_to_alloydb \
  --images outputs/disease_images_info.csv \
  --schema <SCHEMA_NAME> \
  --table disease_images_info \
  --populate-embeddings \


8. **Create merged table + TVF via Python**
python -m scripts.create_merged_and_tvf   --schema <SCHEMA_NAME>   --details-table disease_details_info   --tests-table disease_tests_info   --images-table disease_images_info   --merged-table disease_info_merged   --drop-existing-merged   --tvf-sql sql/search_medical_info.sql



