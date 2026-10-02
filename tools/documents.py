"""Document tools: extract_text, ocr_image, read_section, verify_quote.

Uploaded files are processed in memory only and never written to disk.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from core import llm
from core.config import settings


class OCRUnavailable(RuntimeError):
    pass


class UnsupportedDocument(ValueError):
    pass


@dataclass
class ExtractedDocument:
    text: str
    is_scanned: bool
    pages: int
    kind: str  # pdf | image | text


def extract_text(data: bytes, filename: str = "") -> ExtractedDocument:
    """Text layer of a PDF (pdfplumber), or plain text. Flags scanned PDFs and images for OCR."""
    name = filename.lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
        except Exception as e:
            raise UnsupportedDocument("the PDF could not be opened (corrupt or password-protected)") from e
        text = "\n\n".join(pages).strip()
        chars_per_page = len(re.sub(r"\s", "", text)) / max(len(pages), 1)
        return ExtractedDocument(text=text, is_scanned=chars_per_page < 60, pages=len(pages), kind="pdf")
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or name.endswith((".png", ".jpg", ".jpeg")):
        return ExtractedDocument(text="", is_scanned=True, pages=1, kind="image")
    if name.endswith((".txt", ".md")) or _looks_like_text(data):
        return ExtractedDocument(text=data.decode("utf-8", errors="replace"), is_scanned=False, pages=1, kind="text")
    raise UnsupportedDocument("please upload a PDF, an image (PNG/JPG) or a text file")


def _looks_like_text(data: bytes) -> bool:
    sample = data[:2000]
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return b"\x00" not in sample


def page_images(data: bytes, kind: str, max_pages: int = 6) -> list[bytes]:
    """PNG bytes for each page (PDF pages rendered at ~200 dpi, or the image itself)."""
    if kind == "image":
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return [buf.getvalue()]
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    out = []
    for i in range(min(len(pdf), max_pages)):
        pil = pdf[i].render(scale=150 / 72).to_pil()  # 150 dpi: enough for OCR, ~2x faster than 200
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def ocr_image(page_png: bytes, meter: llm.TokenMeter | None = None) -> str:
    """OCR one page: Tesseract when installed, otherwise the Claude vision model."""
    if settings.tesseract_available:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(page_png)))
    if not settings.offline:
        return llm.text_call(
            model=settings.fast_model,
            system="You transcribe scanned documents. Output only the text on the page, preserving line breaks. "
                   + llm.DATA_ONLY_RULE,
            prompt="Transcribe this page exactly.",
            images=[page_png],
            meter=meter,
        )
    raise OCRUnavailable("this looks like a scanned letter; OCR needs Tesseract or a Claude API key")


# --------------------------------------------------------------------------- sections

SECTION_KEYWORDS: dict[str, list[str]] = {
    "company": ["private limited", "pvt", "ltd", "limited", "technologies", "letterhead", "on behalf of", "welcome to",
                "regards"],
    "role": ["designation", "position", "role", "post of", "appointed as", "trainee", "engineer", "analyst"],
    "batch": ["batch", "graduat", "passing out", "campus", "date of joining", "joining date"],
    "compensation": ["ctc", "cost to company", "salary", "remuneration", "compensation", "package", "per annum", "lpa",
                     "stipend", "gross"],
    "bond": ["bond", "service agreement", "service commitment", "minimum period", "serve the company",
             "continuous service", "commitment", "lock-in", "lock in", "tenure"],
    "penalty": ["liquidated damages", "penalty", "pay the company", "pay an amount", "compensate", "reimburse",
                "liable to pay", "recover", "damages", "bond amount", "sum of"],
    "prorated": ["pro-rata", "pro rata", "proportionate", "prorated", "pro-rated", "remaining period",
                 "unserved", "balance period"],
    "notice": ["notice period", "notice", "resign", "resignation", "termination", "relieving"],
    "training": ["training cost", "training expenses", "cost of training", "training fee", "investment in training"],
    "certificates": ["original certificate", "original documents", "certificates", "mark sheets", "marksheets",
                     "retain", "custody", "deposit"],
    "risky": ["withheld", "forfeit", "deduct", "without notice", "no salary", "non-compete", "non compete",
              "relocation", "any location", "shift", "blank cheque", "cheque", "surety", "guarantor", "probation"],
}


_ENUM = re.compile(r"^\s*(?:\d{1,2}[.)]|[a-z][.)]|\([a-z0-9]+\)|clause\s+\d)\s", re.I)


def split_clauses(text: str) -> list[str]:
    """Paragraphs / numbered clauses, the unit that read_section returns and quotes come from.

    A line starting with '1.' or '(a)' only starts a new clause when the previous line ended a
    sentence or was a short heading, so a wrapped '(1) year.' stays inside its sentence.
    """
    blocks: list[list[str]] = [[]]
    prev = ""
    for line in text.split("\n"):
        if not line.strip():
            blocks.append([])
        elif _ENUM.match(line) and blocks[-1] and (re.search(r"[.;:!?]\s*$", prev) or len(prev.strip()) < 60):
            blocks.append([line])
        else:
            blocks[-1].append(line)
        prev = line
    out = []
    for b in blocks:
        s = re.sub(r"[ \t]+", " ", "\n".join(b)).strip()
        if len(s) > 3:
            out.append(s)
    return out


def read_section(text: str, section: str, max_chars: int = 2500) -> str:
    """The clauses most relevant to `section` (e.g. 'bond', 'penalty', 'notice'), best first."""
    kws = SECTION_KEYWORDS.get(section, [section])
    scored = []
    for i, clause in enumerate(split_clauses(text)):
        low = clause.lower()
        score = sum(low.count(k) for k in kws)
        if score:
            scored.append((score, i, clause))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out, size = [], 0
    for _, _, clause in scored:
        if size + len(clause) > max_chars and out:
            break
        out.append(clause)
        size += len(clause)
    return "\n\n".join(out)


# --------------------------------------------------------------------------- verification

def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = re.sub(r"[^\w₹%/.,'\-\[\] ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def verify_quote(quote: str, document: str, threshold: float = 92.0) -> dict:
    """Does `quote` really appear in `document`? Exact (whitespace/case-insensitive) or near-exact match."""
    if not quote or not quote.strip():
        return {"found": False, "score": 0.0, "reason": "empty quote"}
    q, d = _norm(quote), _norm(document)
    if len(q) < 4:
        return {"found": False, "score": 0.0, "reason": "quote too short to verify"}
    if q in d:
        return {"found": True, "score": 100.0}
    score = fuzz.partial_ratio(q, d) if len(q) <= 600 else 0.0
    return {"found": score >= threshold, "score": round(score, 1),
            "reason": None if score >= threshold else "quote not found in document"}
