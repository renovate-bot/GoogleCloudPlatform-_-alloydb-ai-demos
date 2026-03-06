from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
import io
import base64
import fitz
from PIL import Image


def extract_disease_images(pdf_path: Path, output_dir: Path) -> Dict[str, List[Dict[str, object]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    disease_data: Dict[str, List[Dict[str, object]]] = {}
    current_disease = "Unknown_Disease"
    image_buffer: List[Image.Image] = []

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        blocks.sort(key=lambda b: b["bbox"][1])
        for block in blocks:
            if block["type"] == 1:
                image_bytes = block["image"]
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    image_buffer.append(img)
                except Exception as e:
                    print(f"Error loading image on page {page_num}: {e}")
            elif block["type"] == 0:
                block_text = " ".join(span["text"] for line in block["lines"] for span in line["spans"]).strip()
                lower = block_text.lower()
                if lower.startswith("disease :") or lower.startswith("disease:"):
                    parts = block_text.split(":", 1)
                    if len(parts) > 1:
                        current_disease = parts[1].strip()
                    image_buffer = []
                elif lower.startswith("caption :") or lower.startswith("caption:"):
                    caption_text = block_text
                    if image_buffer:
                        entry = {"caption": caption_text, "images": list(image_buffer)}
                        disease_data.setdefault(current_disease, []).append(entry)
                        save_images_to_disk(current_disease, image_buffer, output_dir)
                        image_buffer = []
                    else:
                        print(f"Warning: Caption found for '{current_disease}' but no image preceded it.")
    doc.close()
    return disease_data


def save_images_to_disk(disease_name: str, images: List[Image.Image], base_dir: Path) -> None:
    safe = "".join(x for x in disease_name if x.isalnum() or x in " _-").strip()
    folder = base_dir / safe
    folder.mkdir(parents=True, exist_ok=True)
    existing = len(list(folder.glob('*.png')))
    for i, img in enumerate(images):
        (folder / f"image_{existing + i + 1}.png").write_bytes(_img_to_png_bytes(img))


def _img_to_png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return buf.getvalue()


def pil_to_base64_png(im: Image.Image, max_width: Optional[int] = None) -> str:
    img = im
    if max_width and hasattr(img, 'width') and img.width > max_width:
        ratio = max_width / float(img.width)
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)
    return base64.b64encode(_img_to_png_bytes(img)).decode('utf-8')
