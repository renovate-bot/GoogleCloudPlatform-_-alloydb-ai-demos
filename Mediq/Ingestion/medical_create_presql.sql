--this table contain data for disease name and test name
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS google_ml_integration;


-- AFTER DATA LOADED INTO THE TABLE
ALTER TABLE :"schema_name".disease_tests_info 
ADD COLUMN disease_name_embedding VECTOR(768); 

UPDATE :"schema_name".disease_tests_info

SET disease_name_embedding = google_ml.embedding('text-embedding-005', disease_name);
