"""
CLI to pull the MIMIC-IV demo Croissant dataset from Kaggle and materialize
select CSVs locally using mlcroissant. Also provides a helper to build
`disease_tests_info.csv` by merging the four demo CSVs.
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
        df.columns = df.columns.str.replace(rf'^{re.escape(fname)}/', '', regex=True)
        df = df.apply(lambda col: col.map(lambda x: x.decode('utf-8') if isinstance(x, (bytes, bytearray)) else x))

        (out_dir / fname).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / fname, index=False)
        print(f"Wrote {fname} -> {out_dir/fname} (rows={len(df)})")


def build_disease_tests_info(labitems_csv: Path, labevents_csv: Path, icd_csv: Path, diagnoses_csv: Path, out_csv: Path) -> None:
    """Build consolidated disease_tests_info.csv from the four MIMIC demo CSVs.

    Steps:
      1) diagnoses_icd + d_icd_diagnoses on ['icd_code','icd_version']
      2) + labevents on 'hadm_id'
      3) + d_labitems on 'itemid'
      4) Select unique combinations and rename columns as required.
    """
    d_labitems_df = pd.read_csv(labitems_csv)
    labevents_df = pd.read_csv(labevents_csv)
    d_icd_diagnoses_df = pd.read_csv(icd_csv)
    diagnoses_icd_df = pd.read_csv(diagnoses_csv)

    labevents_df['hadm_id'] = pd.to_numeric(labevents_df['hadm_id'], errors='coerce').astype('Int64')

    merged_diagnoses_df = pd.merge(diagnoses_icd_df, d_icd_diagnoses_df, on=['icd_code','icd_version'], how='inner')
    merged_diagnoses_labevents_df = pd.merge(merged_diagnoses_df, labevents_df, on='hadm_id', how='inner')
    final_merged_df = pd.merge(merged_diagnoses_labevents_df, d_labitems_df, on='itemid', how='inner')

    unique_combos = final_merged_df[['long_title','label','fluid','category']].drop_duplicates()
    unique_combos = unique_combos.rename(columns={
        'long_title': 'disease_name_csv',
        'label': 'test_name',
        'fluid': 'test_type',
        'category': 'test_category',
    })
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    unique_combos.to_csv(out_csv, index=False)
    print(f"Created disease_tests_info.csv -> {out_csv} (rows={len(unique_combos)})")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pull Kaggle Croissant demo CSVs and optionally build disease_tests_info.csv")
    p.add_argument('--dataset-url', required=True, help='Kaggle Croissant dataset URL (download endpoint)')
    p.add_argument('--files', nargs='+', required=True, help='List of CSV file names to materialize')
    p.add_argument('--out-dir', type=Path, required=True, help='Directory to write CSVs')
    p.add_argument('--build-tests-info', action='store_true', help='After materialization, merge the four files to create disease_tests_info.csv')
    p.add_argument('--tests-info-out', type=Path, default=Path('disease_tests_info.csv'), help='Output path for disease_tests_info.csv')
    return p.parse_args()


def main() -> None:
    args = parse_args()
    materialize(args.dataset_url, args.files, args.out_dir)

    if args.build_tests_info:
        base = args.out_dir
        # Expect standard file names (same as provided in --files)
        build_disease_tests_info(
            base / 'd_labitems.csv',
            base / 'labevents.csv',
            base / 'd_icd_diagnoses.csv',
            base / 'diagnoses_icd.csv',
            args.tests_info_out,
        )


if __name__ == '__main__':
    main()
