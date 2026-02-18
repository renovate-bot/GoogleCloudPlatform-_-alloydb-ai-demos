"""
CLI to pull the MIMIC-IV demo Croissant dataset from Kaggle and materialize
select CSVs locally using mlcroissant. Also provides a helper to build a
grouped disease_tests_info.csv
"""

from __future__ import annotations
import argparse
from pathlib import Path
import re
import pandas as pd
import mlcroissant as mlc


def materialize(dataset_url: str, filenames: list[str], out_dir: Path) -> None:
    """Download/read a Croissant dataset and write selected files as CSVs.

    Args:
        dataset_url: Croissant dataset URL from Kaggle (the ".../croissant/download" URL).
        filenames: List of target file names to extract (e.g., ["d_labitems.csv"]).
        out_dir: Directory to write CSVs into.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ds = mlc.Dataset(dataset_url)

    for fname in filenames:
        target_uuid = None
        for rs in ds.metadata.record_sets:
            if fname.lower() in rs.name.lower():
                target_uuid = rs.uuid
                break
        if target_uuid is None:
            raise FileNotFoundError(f"{fname} not found in Croissant record sets")

        df = pd.DataFrame(ds.records(record_set=target_uuid))
        # Strip "<file>/" prefixes from column names
        df.columns = df.columns.str.replace(rf'^{re.escape(fname)}/', '', regex=True)
        # Decode potential byte columns
        df = df.apply(
            lambda col: col.map(
                lambda x: x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
            )
        )
        (out_dir / fname).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / fname, index=False)
        print(f"Wrote {fname} -> {out_dir/fname} (rows={len(df)})")


def _simplify_disease_name(disease_name_csv_long: str) -> str:
    """Heuristic to derive a simpler disease_name from disease_name_csv_long.
    Examples:
      "Gout, unspecified"  -> "Gout"
      "Acute kidney failure (unspecified)" -> "Acute kidney failure"
    """
    if not isinstance(disease_name_csv_long, str):
        return ""
    # Take text before the first comma or opening parenthesis
    s = disease_name_csv_long.strip()
    s = s.split(",", 1)[0]
    s = s.split("(", 1)[0]
    return s.strip() or disease_name_csv_long.strip()


def build_disease_tests_info_grouped(
    labitems_csv: Path,
    labevents_csv: Path,
    icd_csv: Path,
    diagnoses_csv: Path,
    out_csv: Path,
) -> None:
    """Build grouped disease_tests_info.csv from the four MIMIC demo CSVs.
    Steps:
      1) diagnoses_icd + d_icd_diagnoses on ['icd_code','icd_version']
      2) + labevents on 'hadm_id'
      3) + d_labitems on 'itemid'
      4) Group by disease (ICD long_title) and collect unique test labels (d_labitems.label)
      5) Write columns in the SAME schema as your attached CSV:
         ['disease_name_csv_long','disease_name','test_name']
    - test_name is written as a single string that looks like a Python list,
    - disease_name is a simplified version of disease_name_csv_long (heuristic).
    """
    # Load sources
    d_labitems_df = pd.read_csv(labitems_csv)
    labevents_df = pd.read_csv(labevents_csv)
    d_icd_diagnoses_df = pd.read_csv(icd_csv)
    diagnoses_icd_df = pd.read_csv(diagnoses_csv)

    # Ensure hadm_id numeric (nullable)
    labevents_df['hadm_id'] = pd.to_numeric(labevents_df['hadm_id'], errors='coerce').astype('Int64')

    # Merge to associate diagnoses -> admissions -> lab items
    merged_diagnoses_df = pd.merge(
        diagnoses_icd_df,
        d_icd_diagnoses_df,
        on=['icd_code', 'icd_version'],
        how='inner',
    )
    merged_diagnoses_labevents_df = pd.merge(
        merged_diagnoses_df,
        labevents_df,
        on='hadm_id',
        how='inner',
    )
    final_merged_df = pd.merge(
        merged_diagnoses_labevents_df,
        d_labitems_df,
        on='itemid',
        how='inner',
    )

    # We only need the long diagnostic title and the test label
    # long_title -> disease_name_csv_long; label -> test label
    # Drop NAs, normalize test names, and aggregate
    subset = (
        final_merged_df[['long_title', 'label']]
        .dropna()
        .rename(columns={'long_title': 'disease_name_csv_long', 'label': 'test_label'})
    )

    # Make tests unique, clean whitespace, and sort for determinism
    subset['test_label'] = subset['test_label'].map(lambda x: str(x).strip())
    grouped = (
        subset.groupby('disease_name_csv_long', as_index=False)['test_label']
        .agg(lambda s: sorted(set([t for t in s if t])))
    )

    # Convert list to a single string exactly like Python list literal to mirror your CSV
    grouped['test_name'] = grouped['test_label'].map(lambda lst: str(lst))
    grouped.drop(columns=['test_label'], inplace=True)

    # Derive simplified disease_name
    grouped['disease_name_csv'] = grouped['disease_name_csv_long'].map(_simplify_disease_name)

    out_df = grouped[['disease_name_csv_long', 'disease_name_csv', 'test_name']].copy()
    #out_df.drop(columns=["disease_name_csv_long"], inplace=True)


    # Persist
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_csv, index=False, encoding='utf-8')
    print(f"Created grouped disease_tests_info.csv -> {out_csv} (rows={len(out_df)})")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pull Kaggle Croissant demo CSVs and optionally build grouped disease_tests_info.csv"
    )
    p.add_argument('--dataset-url', required=True, help='Kaggle Croissant dataset URL (download endpoint)')
    p.add_argument('--files', nargs='+', required=True, help='List of CSV file names to materialize')
    p.add_argument('--out-dir', type=Path, required=True, help='Directory to write CSVs')

    p.add_argument(
        '--build-tests-info',
        action='store_true',
        help='After materialization, merge files to create grouped disease_tests_info.csv',
    )
    p.add_argument(
        '--tests-info-out',
        type=Path,
        default=Path('disease_tests_info.csv'),
        help='Output path for the grouped disease_tests_info.csv',
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    materialize(args.dataset_url, args.files, args.out_dir)

    if args.build_tests_info:
        base = args.out_dir
        # Expect standard file names (same as provided in --files)
        build_disease_tests_info_grouped(
            base / 'd_labitems.csv',
            base / 'labevents.csv',
            base / 'd_icd_diagnoses.csv',
            base / 'diagnoses_icd.csv',
            args.tests_info_out,
        )


if __name__ == '__main__':
    main()