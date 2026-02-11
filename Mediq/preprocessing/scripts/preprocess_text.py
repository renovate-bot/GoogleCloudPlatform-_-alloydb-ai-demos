"""
PDF+CSV preprocessing to chunked CSV.
"""

from __future__ import annotations
import argparse
import logging
import time
from pathlib import Path
from src.medical_preprocess.io_utils.csv_io import (
    load_disease_list,
    write_chunks_csv,
    write_unmatched_csv,
    filter_original_csv_to_matched,
)
from src.medical_preprocess.data.pdf_text_extractor import chunk_for_diseases, extract_pdf_lines, detect_headings

def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with timestamps and levels."""
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, level.upper(), logging.INFO),
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
    p.add_argument('--filter-original-in-place', action='store_true',
                   help='Filter original CSV in place to matched diseases')  
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

    # STEP 1: Load disease list
    t0 = time.perf_counter()
    log.info("[1/5] Loading disease list from CSV ...")
    diseases = load_disease_list(str(args.csv))
    log.info("Loaded %d diseases in %.2fs", len(diseases), time.perf_counter() - t0)

    # STEP 2: Chunk PDF by matched headings
    t1 = time.perf_counter()
    log.info("[2/5] Extracting disease chunks from PDF ...")
    records, unmatched = chunk_for_diseases(
        pdf_path=args.pdf,
        diseases=diseases,
        threshold=args.match_threshold,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    log.info(
        "Chunking done in %.2fs | records=%d | unmatched=%d",
        time.perf_counter() - t1, len(records), len(unmatched)
    )

    # STEP 3: Write outputs
    t2 = time.perf_counter()
    log.info("[3/5] Writing outputs: chunks CSV & unmatched CSV ...")
    args.out_chunks.parent.mkdir(parents=True, exist_ok=True)
    write_chunks_csv(str(args.out_chunks), records)
    write_unmatched_csv(str(args.out_unmatched), unmatched)
    log.info("Wrote: %s (records=%d), %s (unmatched=%d) in %.2fs",
             args.out_chunks, len(records), args.out_unmatched, len(unmatched),
             time.perf_counter() - t2)

    # STEP 4: Optionally filter original CSV
    if args.filter_original_in_place:
        t3 = time.perf_counter()
        log.info("[4/5] Filtering original CSV in place to matched diseases ...")
        matched = set(diseases) - set(unmatched)
        filter_original_csv_to_matched(str(args.csv), matched)
        log.info("Filtered original CSV -> %s (matched=%d) in %.2fs",
                 args.csv, len(matched), time.perf_counter() - t3)
    else:
        log.debug("[4/5] Skipped filtering original CSV (flag not set)")

    # STEP 5: Optional headings debug dump
    if args.headings_debug:
        t4 = time.perf_counter()
        log.info("[5/5] Dumping detected headings for debugging ...")
        lines = extract_pdf_lines(args.pdf)
        heads = detect_headings(lines)
        with open(args.headings_debug, "w", encoding="utf-8") as f:
            for gi, pno, htxt in heads:
                f.write(f"[page {pno+1} | idx {gi}] {htxt}\n")
        log.info("Headings dump -> %s (count=%d) in %.2fs",
                 args.headings_debug, len(heads), time.perf_counter() - t4)
    else:
        log.debug("[5/5] Skipped headings debug dump (flag not set)")

    log.info("=== Done. Total time: %.2fs ===", time.perf_counter() - start_all)
    log.info(f"Records: {len(records)} | Unmatched: {len(unmatched)}")


if __name__ == '__main__':
    main()
 