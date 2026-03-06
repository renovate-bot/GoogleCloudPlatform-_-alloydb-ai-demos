from __future__ import annotations
import re
import pandas as pd
import mlcroissant as mlc


def load_croissant_file(dataset_url: str, filename: str) -> pd.DataFrame:
    croissant_dataset = mlc.Dataset(dataset_url)
    target_record_set = None
    for rs in croissant_dataset.metadata.record_sets:
        if filename in rs.name.lower():
            target_record_set = rs
            break
    if not target_record_set:
        raise FileNotFoundError(f"{filename} not found in record sets")

    df = pd.DataFrame(croissant_dataset.records(record_set=target_record_set.uuid))
    df.columns = df.columns.str.replace(rf'^{re.escape(filename)}/', '', regex=True)
    df = df.apply(lambda col: col.map(lambda x: x.decode('utf-8') if isinstance(x, (bytes, bytearray)) else x))

    id_cols = [c for c in df.columns if 'id' in c.lower()]
    for c in id_cols:
        df[c] = df[c].apply(lambda x: pd.to_numeric(str(x).strip(), errors='coerce') if str(x).strip().isdigit() else str(x).strip())
    return df
