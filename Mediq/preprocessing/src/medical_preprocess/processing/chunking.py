from __future__ import annotations
from typing import Dict, List, Tuple
import re
import difflib

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except Exception:
    from langchain_text_splitters import RecursiveCharacterTextSplitter


def normalize_text(s: str) -> str:
    s = s.lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"[^a-z0-9\s()\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fuzz_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def clean_block_text(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned: List[str] = []
    prev_blank = False
    for ln in lines:
        if ln.strip() == "":
            if not prev_blank:
                cleaned.append("")
                prev_blank = True
        else:
            cleaned.append(ln.strip())
            prev_blank = False
    return "\n".join(cleaned).strip()


def chunk_text_by_page(page_texts: Dict[int, str], chunk_size: int = 1000, chunk_overlap: int = 100) -> List[Tuple[int, str]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
       separators=[
            "\n\n", "\n", " ", ""  # progressively finer splits
        ],
    )
    out: List[Tuple[int, str]] = []
    for pno in sorted(page_texts.keys()):
        txt = clean_block_text(page_texts[pno])
        if not txt:
            continue
        for ch in splitter.split_text(txt):
            if ch.strip():
                out.append((pno, ch.strip()))
    return out
