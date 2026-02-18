"""
Extract disease images and captions from a PDF and output a CSV with base64 PNG.
"""

from __future__ import annotations
import argparse
from pathlib import Path
from src.medical_preprocess.data.pdf_image_extractor import extract_disease_images, pil_to_base64_png
import csv


def _sanitize_for_csv(s: str) -> str:
    """
    # Prevent CSV/Excel formula injection if users open the CSV.
    Excel treats cells starting with = + - @ as formulas.
    We prefix a single quote to neutralize.
    """
    s = (s or "").strip()
    if not s:
        return ""
    if s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


def main() -> None:
    p = argparse.ArgumentParser(description="Extract disease images and captions from a PDF")
    p.add_argument('--pdf', required=True, type=Path)
    p.add_argument('--out-dir', required=True, type=Path, help='Directory to write images per disease')
    p.add_argument('--out-csv', required=True, type=Path, help='CSV to write (disease_name, caption_text, disease_image_base64)')
    args = p.parse_args()

    # Ensure output directory exists.
    args.out_dir.mkdir(parents=True, exist_ok=True)

    data = extract_disease_images(args.pdf, args.out_dir)

    rows = []
    for disease, items in data.items():
        for item in items:
            caption_raw = (item.get('caption') or '').strip()
            if caption_raw.lower().startswith('caption'):
                parts = caption_raw.split(':', 1)
                caption_text = parts[1].strip() if len(parts) > 1 else caption_raw
            else:
                caption_text = caption_raw

            caption_text = _sanitize_for_csv(caption_text)  # NEW
            images = item.get('images') or []

            if not images:
                rows.append({
                    'disease_name': disease,
                    'caption_text': caption_text,
                    'disease_image_base64': '',  
                })
            else:
                for im in images:
                    rows.append({
                        'disease_name': disease,
                        'caption_text': caption_text,
                        'disease_image_base64': pil_to_base64_png(im, max_width=1400),
                    })

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['disease_name', 'caption_text', 'disease_image_base64'])
        w.writeheader()
        w.writerows(rows)

    print(f"Prepared {len(rows)} rows for DB insert.")


if __name__ == '__main__':
    main()
 