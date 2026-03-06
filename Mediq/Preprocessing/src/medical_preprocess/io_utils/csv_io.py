from __future__ import annotations
from typing import Dict, List, Sequence, Set
import csv
import pandas as pd
from ..processing.chunking import normalize_text


def load_disease_list(csv_path: str) -> List[str]:
    df = pd.read_csv(csv_path)
    col = 'disease_name' if 'disease_name' in df.columns else df.columns[0]
    return [str(x).strip() for x in df[col].fillna('') if str(x).strip()]


def write_chunks_csv(out_csv_path: str, records: List[Dict[str, object]]) -> None:
    header = ["disease_name", "chunk_content", "chunk_num", "chunk_page_no"]
    with open(out_csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in records:
            w.writerow([r.get(h, '') for h in header])


def write_unmatched_csv(out_path: str, unmatched: Sequence[str]) -> None:
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['disease_name'])
        for d in unmatched:
            w.writerow([d])


def filter_original_csv_to_matched(original_csv_path: str, matched_diseases: Set[str]) -> None:
    df = pd.read_csv(original_csv_path)
    #name_col = 'disease_name' 
    #matched_norm = {normalize_text(d) for d in matched_diseases}
    #log.info("Matched norm: %s",matched_norm)
    #def _keep(val: object) -> bool:
    #    return normalize_text(str(val)) in matched_norm
    #filtered = df.copy()   
    #filtered['disease_name'] = [matched_norm]
    if 'disease_name' in df.columns:
        name_col = 'disease_name'
    else:
        name_col = df.columns[0]
    matched_norm = {normalize_text(d) for d in matched_diseases}
    def _keep(val: object) -> bool:
        return normalize_text(str(val)) in matched_norm
    filtered = df[df[name_col].apply(_keep)].copy()

    filtered.to_csv(original_csv_path, index=False, encoding='utf-8')
