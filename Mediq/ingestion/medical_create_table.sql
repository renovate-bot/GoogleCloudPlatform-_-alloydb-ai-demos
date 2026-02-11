--This table contain data for disease name and test name
CREATE SCHEMA IF NOT EXISTS :"schema_name";
CREATE TABLE IF NOT EXISTS :"schema_name".disease_tests_info (
  disease_name_csv        TEXT NOT NULL,
  disease_name            TEXT NOT NULL,
  test_name               TEXT
);