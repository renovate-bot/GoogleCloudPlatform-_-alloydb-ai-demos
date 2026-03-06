"""
PDF+CSV preprocessing to chunked CSV with a pre-step that finds common diseases
between the encyclopedia PDF index and disease_tests_info.csv.

Flow:
  [1] Load disease candidates from CSV
  [2A] Run common-disease finder -> result_sheet + filtered CSV 
  [2B] Build list of diseases for chunking from the filtered CSV
  [3] Chunk the PDF for those diseases
  [4] Write outputs (chunks, unmatched)
  [5] Optional: filter original CSV in place
  [6] Optional: headings debug dump
"""

from __future__ import annotations
import argparse
import logging
import time
import pandas as pd
from pathlib import Path
from src.medical_preprocess.io_utils.csv_io import (
    load_disease_list,
    write_chunks_csv,
    write_unmatched_csv,
    filter_original_csv_to_matched,
)
from src.medical_preprocess.data.pdf_text_extractor import (
    chunk_for_diseases,
    extract_pdf_lines,
    detect_headings,
)

from src.medical_preprocess.processing.common_disease_finder import (
    FinderConfig,
    find_common_diseases,
)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with timestamps and levels."""
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def _diseases_from_filtered_df(filtered_df) -> List[str]:
    """
    Extract the diseases to send to the chunker from filtered DataFrame.

    We use 'disease_name_csv' (the CSV-side names) to stay aligned with the
    PDF heading-fuzzy-matching inside chunk_for_diseases.
    """
    if filtered_df is None or filtered_df.empty:
        return []
    col = "disease_name_csv" if "disease_name_csv" in filtered_df.columns else (
        "disease_name" if "disease_name" in filtered_df.columns else filtered_df.columns[0]
    )
    return sorted(
        {
            str(x).strip()
            for x in filtered_df[col].fillna("")
            if str(x).strip()
        }
    )


def main() -> None:
    p = argparse.ArgumentParser(description="PDF+CSV preprocessing to chunked CSV")
    p.add_argument('--pdf', required=True, type=Path, help='Path to source PDF')
    p.add_argument('--csv', required=True, type=Path, help='Path to disease tests CSV')
    p.add_argument('--out-chunks', required=True, type=Path, help='Output chunks CSV path')
    p.add_argument('--out-unmatched', required=True, type=Path, help='Output unmatched CSV path')
    p.add_argument('--headings-debug', required=False, type=Path, help='Optional headings debug txt path')
    p.add_argument('--chunk-size', type=int, default=1000)
    p.add_argument('--chunk-overlap', type=int, default=100)
    p.add_argument('--match-threshold', type=float, default=0.6, help='Fuzzy match threshold [0,1]')  

    p.add_argument(
        '--use-vertex-matcher',
        action="store_true",
        help="Use Vertex AI Gemini to find diseases in PDF index (default False). "
             "If not set, a headings-based fuzzy pre-match will be used.",
    )
    p.add_argument('--vertex-project-id', default=None, help="GCP project for Vertex AI (required if --use-vertex-matcher)")
    p.add_argument('--vertex-location', default="us-central1", help="Vertex location (default: us-central1)")
    p.add_argument('--vertex-model', default="gemini-2.5-flash", help="Vertex model name (default: gemini-2.5-flash)")
    p.add_argument('--index-page-start', type=int, default=9, help="0-based inclusive page index for PDF index start")
    p.add_argument('--index-page-end', type=int, default=21, help="0-based exclusive page index for PDF index end")
    p.add_argument('--prematch-threshold', type=float, default=0.62,
                   help="Fuzzy pre-match threshold [0,1] when --use-vertex-matcher is not used")
    p.add_argument('--filter-original-in-place', action='store_true',
                   help='Filter original CSV in place to matched diseases')  
    p.add_argument(
        '--out-common-matches',
        type=Path,
        default=Path("outputs/result_sheet.csv"),
        help="(Optional) Write common-disease pairs here",
    )
    p.add_argument(
        '--out-common-filtered',
        type=Path,
        default=Path("outputs/disease_tests_info_filtered.csv"),
        help="(Optional) Write filtered tests CSV; chunking will use this",
    )


    p.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR",
    )
    args = p.parse_args()
    setup_logging(args.log_level)
    log = logging.getLogger("preprocess_text")

    start_all = time.perf_counter()
    log.info("=== Start preprocessing ===")
    log.info("Inputs: pdf=%s, csv=%s", args.pdf, args.csv)
    log.debug("Params: chunk_size=%d, chunk_overlap=%d, match_threshold=%.2f",
              args.chunk_size, args.chunk_overlap, args.match_threshold)

    # STEP [1]: Load disease list (for visibility/logging)
    t0 = time.perf_counter()
    log.info("[1/6] Loading disease list from CSV ...")
    diseases_full = load_disease_list(str(args.csv))
    log.info("Loaded %d disease candidates in %.2fs", len(diseases_full), time.perf_counter() - t0)

    # STEP [2]: COMMON-DISEASE PRE-STEP (default ON)
    filtered_df = None
    result_df = None

    log.info("[2/6] Running common-disease finder (PDF index ↔ CSV) ...")
    # Configure the finder, defaulting to headings-based pre-match unless Vertex is requested.
    cfg = FinderConfig(
        pdf_path=args.pdf,
        tests_csv=args.csv,
        project_id=args.vertex_project_id,
        location=args.vertex_location,
        model_name=args.vertex_model,
        page_start=args.index_page_start,
        page_end=args.index_page_end,
        prematch_threshold=args.prematch_threshold,
        use_vertex=args.use_vertex_matcher,
        )
    t2 = time.perf_counter()
    result_df, filtered_df = find_common_diseases(cfg)  # returns (result_df, filtered_df)
    log.info("Common-disease step produced: matches=%d, filtered_rows=%d in %.2fs",
             0 if result_df is None else len(result_df),
             0 if filtered_df is None else len(filtered_df),
             time.perf_counter() - t2)

    args.out_common_matches.parent.mkdir(parents=True, exist_ok=True)
    args.out_common_filtered.parent.mkdir(parents=True, exist_ok=True)
    if result_df is not None:
      result_df.to_csv(args.out_common_matches, index=False)
      log.info("Wrote common-disease matches -> %s", args.out_common_matches)
    if filtered_df is not None:
        filtered_df.to_csv(args.out_common_filtered, index=False)
        log.info("Wrote filtered tests CSV -> %s", args.out_common_filtered)

    # Build disease list for chunking from filtered_df; fall back to full list if no matches
    diseases_for_chunk = _diseases_from_filtered_df(filtered_df)
    if not diseases_for_chunk:
      log.warning("No matched diseases after common-disease step; falling back to full CSV list.")
      diseases_for_chunk = diseases_full

    # STEP [3]: Chunk PDF for the chosen diseases
    t3 = time.perf_counter()
    log.info("[3/6] Extracting disease chunks from PDF ...")
    records, unmatched = chunk_for_diseases(
        pdf_path=args.pdf,
        diseases=diseases_for_chunk,
        threshold=args.match_threshold,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    log.info("Chunking done in %.2fs | records=%d | unmatched=%d",
             time.perf_counter() - t3, len(records), len(unmatched))

    # STEP [4]: Write outputs (chunks + unmatched)
    t4 = time.perf_counter()
    log.info("[4/6] Writing outputs: chunks CSV & unmatched CSV ...")
    args.out_chunks.parent.mkdir(parents=True, exist_ok=True)
    write_chunks_csv(str(args.out_chunks), records)
    write_unmatched_csv(str(args.out_unmatched), unmatched)
    log.info("Wrote: %s (records=%d), %s (unmatched=%d) in %.2fs",
             args.out_chunks, len(records), args.out_unmatched, len(unmatched),
             time.perf_counter() - t4)


    # STEP [5]: Optionally filter original CSV in place   
    t5 = time.perf_counter()
    log.info("[5/6] Filtering original CSV in place to matched diseases ...")
    matched = set(diseases_for_chunk) - set(unmatched)
    filter_original_csv_to_matched(str(args.csv), matched)
    log.info("Filtered original CSV -> %s (matched=%d) in %.2fs",
                 args.csv, len(matched), time.perf_counter() - t5)

    # STEP [6]: Optional headings debug dump
    if args.headings_debug:
        t6 = time.perf_counter()
        log.info("[6/6] Dumping detected headings for debugging ...")
        lines = extract_pdf_lines(args.pdf)
        heads = detect_headings(lines)
        with open(args.headings_debug, "w", encoding="utf-8") as f:
            for gi, pno, htxt in heads:
                f.write(f"[page {pno+1} | idx {gi}] {htxt}\n")
        log.info("Headings dump -> %s (count=%d) in %.2fs",
                 args.headings_debug, len(heads), time.perf_counter() - t6)
    else:
        log.debug("[6/6] Skipped headings debug dump (flag not set)")

    log.info("=== Done. Total time: %.2fs ===", time.perf_counter() - start_all)
    log.info(f"Records: {len(records)} | Unmatched: {len(unmatched)}")


if __name__ == '__main__':
    main()