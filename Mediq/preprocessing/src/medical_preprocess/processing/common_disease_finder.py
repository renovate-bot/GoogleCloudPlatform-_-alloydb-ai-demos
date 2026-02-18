"""
Common disease finder between an encyclopedia PDF and disease_tests_info.csv.
(LLM-assisted)
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import pandas as pd
import fitz

try:
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel
except Exception:
    vertex_init = None
    GenerativeModel = None

from .chunking import normalize_text, fuzz_ratio
from ..data.pdf_text_extractor import extract_pdf_lines, detect_headings

log = logging.getLogger("common_disease_finder")

@dataclass(frozen=True)
class FinderConfig:
    pdf_path: Path
    tests_csv: Path
    project_id: Optional[str] = None
    location: str = "us-central1"
    model_name: str = "gemini-2.5-flash"
    page_start: int = 9
    page_end: int = 21
    prematch_threshold: float = 0.62
    use_vertex: bool = True

def _read_index_text(pdf_path: Path, page_start: int, page_end: int) -> str:
    doc = fitz.open(str(pdf_path))
    page_start = max(0, page_start)
    page_end = min(len(doc), page_end)
    parts: List[str] = []
    for p in range(page_start, page_end):
        parts.append(doc[p].get_text("text"))
    doc.close()
    return "\n".join(parts)

def _load_diseases_from_csv(tests_csv: Path) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(tests_csv)
    if 'disease_name_csv' not in df.columns:
        raise ValueError("Expected 'disease_name_csv' in tests CSV")
    diseases = sorted({str(x).strip() for x in df['disease_name_csv'].dropna() if str(x).strip()})
    return df, diseases

def _vertex_match_single(model: 'GenerativeModel', disease: str, index_text: str) -> str:
    prompt = f"""
    You are an information extraction assistant.
    You are given raw text extracted from the index of a medical book and a disease name.
    Your task:
    1. Search the provided index text for the exact disease name as well as any of its aliases or abbreviations.
    2. If found, return the only one disease name exactly as it appears in the index (ignore page numbers, formatting artifacts, or extra text).
    3. If not found, return "None".
    4. Do not invent or return diseases that are not present in the index text.
    5. Ensure the output disease corresponds to the input disease (same meaning, no mismatches).
    Input disease:
    {disease}
    Index text:
    {index_text}
    Output format:
    "disease name" (or "None" if not found)
    Important:
    - Output must be in quotes.
    - Use a consistent format for all results.
"""
    try:
        resp = model.generate_content(prompt)
        return (resp.text or "None").strip().strip('"')
    except Exception as e:
        log.warning("Vertex AI generation failed for '%s': %s", disease, e)
        return "None"

def _fallback_prematch(pdf_path: Path, diseases: List[str], threshold: float) -> List[str]:
    lines = extract_pdf_lines(pdf_path)
    heads = detect_headings(lines)
    head_norm = [normalize_text(h[2]) for h in heads]
    keep: List[str] = []
    for d in diseases:
        nd = normalize_text(d)
        score = 0.0
        for hn in head_norm:
            score = max(score, fuzz_ratio(nd, hn))
            if score >= threshold:
                break
        if score >= threshold:
            keep.append(d)
    return keep

def find_common_diseases(cfg: FinderConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    full_df, diseases = _load_diseases_from_csv(cfg.tests_csv)
    log.info("Loaded %d unique diseases from %s", len(diseases), cfg.tests_csv)
    index_text = _read_index_text(cfg.pdf_path, cfg.page_start, cfg.page_end)
    log.info("Index text chars: %d from pages (%d:%d)", len(index_text), cfg.page_start, cfg.page_end)

    candidates = diseases
    if not cfg.use_vertex:
        candidates = _fallback_prematch(cfg.pdf_path, diseases, cfg.prematch_threshold)

    matches: List[Tuple[str, str]] = []
    if cfg.use_vertex:
        if vertex_init is None or GenerativeModel is None:
            raise ImportError("google-cloud-aiplatform is required for Vertex AI")
        if not cfg.project_id:
            raise ValueError("project_id is required when use_vertex=True")
        vertex_init(project=cfg.project_id, location=cfg.location)
        model = GenerativeModel(cfg.model_name)
        for disease in candidates:
            log.info("Disease: %s", disease)
            found = _vertex_match_single(model, disease, index_text)
            if found and found.lower() != 'none' and found.strip():
                log.info("Match found: %s", found)
                matches.append((disease, found.replace('"','')))
    else:
        matches = [(d, d) for d in candidates]

    result_df = pd.DataFrame(matches, columns=["disease_name_csv", "disease_name"]).copy()
    if not result_df.empty:
        counts = result_df['disease_name'].value_counts()
        dup_targets = counts[counts > 1].index
        result_df = result_df[~result_df['disease_name'].isin(dup_targets)].copy()

    matched_names = set(result_df['disease_name_csv'].unique()) if not result_df.empty else set()
    matched_df = full_df[full_df['disease_name_csv'].isin(matched_names)].copy()
    
    # Merge based on the 'disease_name_csv' column
    filtered_df = pd.merge(matched_df, result_df, on="disease_name_csv")
    # filtered_df = filtered_df.drop("disease_name_csv_long", axis=1)
    # remove rows where disease_name_csv appears more than once
    filtered_df_unique = filtered_df[~filtered_df.duplicated(subset="disease_name_csv", keep=False)]
    filtered_df_unique = filtered_df_unique.drop("disease_name_csv_long", axis =1)
    filtered_df_unique["disease_name"] = (filtered_df_unique["disease_name"].str.replace("’", "'").str.replace("'", ""))

    # Reorder columns in the required order
    filtered_df_unique = filtered_df_unique[["disease_name_csv", "disease_name", "test_name"]]

    # Sort by disease_name
    filtered_df_unique = filtered_df_unique.sort_values(by="disease_name").reset_index(drop=True)
    diseases_list = filtered_df["disease_name"]
    diseases_list.to_csv("diseases_list.csv",index= False) # TO GET THE LIST OF DISEASES THAT CAN BE TESTED IN APPLICATION
 
    return result_df, filtered_df_unique
