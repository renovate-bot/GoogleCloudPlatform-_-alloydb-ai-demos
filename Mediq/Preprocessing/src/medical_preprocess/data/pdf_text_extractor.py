from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import fitz
from ..processing.chunking import normalize_text, fuzz_ratio, chunk_text_by_page

HEADER_EXCLUDE_PATTERNS = (
    r"GALE\s+ENCYCLOPEDIA",
    r"LIST\s+OF\s+ENTRIES",
    r"CONTENTS",
    r"INTRODUCTION",
    r"ADVISORS",
    r"CONTRIBUTORS",
    r"KEY\s+TERMS",
    r"Resources",
    r"ORGANIZATIONS",
    r"PERIODICALS",
)


def looks_like_header(line: str) -> bool:
    import re
    for pat in HEADER_EXCLUDE_PATTERNS:
        if re.search(pat, line, flags=re.IGNORECASE):
            return True
    letters = [c for c in line if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.95 and len(line.strip()) >= 12:
            return True
    return False


def is_heading_candidate(curr: str, prev: Optional[str], nxt: Optional[str]) -> bool:
    import re
    s = curr.strip()
    if len(s) < 2 or len(s) > 120:
        return False
    if looks_like_header(s):
        return False
    if s.endswith(":") or s.endswith(".") or s.endswith(";"):
        return False
    letters = [c for c in s if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        lower_ratio = sum(1 for c in letters if c.islower()) / len(letters)
        if upper_ratio > 0.95:
            return False
        if lower_ratio < 0.25 and not (
            nxt and re.match(r"\s*(Definition|Description|Causes and symptoms|Diagnosis|Treatment)\b", nxt)
        ):
            return False
    if len(s.split()) > 16:
        return False
    if nxt and __import__('re').match(r"\s*(Definition|Description|Causes and symptoms|Diagnosis|Treatment|Purpose|Precautions)\b", nxt):
        return True
    if (prev is None or prev.strip() == "") and len(s.split()) <= 10 and any(ch.isalpha() for ch in s):
        return True
    return False


def extract_pdf_lines(pdf_path: Path) -> List[Tuple[int, str]]:
    doc = fitz.open(str(pdf_path))
    all_lines: List[Tuple[int, str]] = []
    for pno in range(len(doc)):
        page = doc[pno]
        txt = page.get_text("text")
        for raw in txt.splitlines():
            line = raw.rstrip(" ")
            if not line.strip():
                all_lines.append((pno, ""))
                continue
            if looks_like_header(line):
                continue
            all_lines.append((pno, line))
    return all_lines


def detect_headings(lines: List[Tuple[int, str]]) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    for i, (pno, text) in enumerate(lines):
        prev = lines[i-1][1] if i > 0 else None
        nxt = lines[i+1][1] if i + 1 < len(lines) else None
        if is_heading_candidate(text, prev, nxt):
            out.append((i, pno, text.strip()))
    return out


def pick_best_heading(disease: str, headings: List[Tuple[int, int, str]], threshold: float = 0.62) -> Optional[Tuple[int, int, str, float]]:
    norm_d = normalize_text(disease)
    best: Optional[Tuple[int, int, str, float]] = None
    for (gi, pno, htxt) in headings:
        score = fuzz_ratio(norm_d, normalize_text(htxt))
        if best is None or score > best[3]:
            best = (gi, pno, htxt, score)
    if best and best[3] >= threshold:
        return best
    return None


def extract_block_lines(lines: List[Tuple[int, str]], start_idx: int, next_heading_idx: Optional[int]) -> List[Tuple[int, str]]:
    end = next_heading_idx if next_heading_idx is not None else len(lines)
    return lines[start_idx:end]


def chunk_for_diseases(
    pdf_path: Path,
    diseases: List[str],
    threshold: float = 0.6,
    chunk_size: int = 1000,
    chunk_overlap: int = 100
) -> Tuple[List[Dict[str, object]], List[str]]:
    lines = extract_pdf_lines(pdf_path)
    headings = detect_headings(lines)
    heading_positions = [gi for gi, _, _ in headings]
    next_heading_after = {}
    for i, gi in enumerate(heading_positions):
        nxt = heading_positions[i+1] if i + 1 < len(heading_positions) else None
        next_heading_after[gi] = nxt

    records: List[Dict[str, object]] = []
    unmatched: List[str] = []

    for disease in diseases:
        pick = pick_best_heading(disease, headings, threshold=threshold)
        if not pick:
            unmatched.append(disease)
            continue
        start_global_idx = pick[0]
        next_idx = next_heading_after.get(start_global_idx)
        block_lines = extract_block_lines(lines, start_global_idx, next_idx)

        by_page = {}
        for pno, ln in block_lines:
            by_page.setdefault(pno, []).append(ln)
        page_texts = {pno: "\n".join(ls) for pno, ls in by_page.items()}

        page_chunks = chunk_text_by_page(page_texts, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        chunk_num = 1
        for pno, chunk_text in page_chunks:
            records.append({
                "disease_name": disease,
                "chunk_content": chunk_text,
                "chunk_num": chunk_num,
                "chunk_page_no": pno + 1,
            })
            chunk_num += 1
    return records, unmatched
