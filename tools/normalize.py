"""Deterministic normalisers used by the Extraction Agent to cross-check values against quotes.

normalize_amount("Rs. 1,50,000/-")                         -> [150000]
normalize_amount("Rupees One Lakh Fifty Thousand only")    -> [150000]
normalize_amount("4.5 LPA")                                -> [450000]
normalize_duration("two (2) years")                        -> 24
"""
from __future__ import annotations

import re

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
           "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000}

_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CUR = r"(?:rs\.?|inr|₹|rupees)"


def words_to_number(text: str) -> int | None:
    """'One Lakh Fifty Thousand' -> 150000. Returns None if no number words found."""
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    total, current, seen = 0, 0, False
    for t in tokens:
        if t in _UNITS:
            current += _UNITS[t]
            seen = True
        elif t in _SCALES:
            scale = _SCALES[t]
            seen = True
            if scale == 100:
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * scale
                current = 0
        elif t in {"and", "only", "rupees", "rs", "inr"}:
            continue
        elif seen:
            break
    return total + current if seen else None


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def normalize_amount(text: str) -> list[int]:
    """All rupee amounts mentioned in `text`, as integers (annualised when stated per month)."""
    if not text:
        return []
    t = text.lower()
    out: list[int] = []
    # 4.5 LPA / 4.5 lakhs per annum / 1.5 lakh / 2 crore
    for m in re.finditer(rf"(?:{_CUR}\s*)?({_NUM})\s*(lpa|lakhs?|lacs?|l\b|crores?|cr\b)", t):
        mult = 10_000_000 if m.group(2).startswith("cr") else 100_000
        out.append(int(round(_to_float(m.group(1)) * mult)))
    # Rs. 1,50,000 / INR 150000 / ₹ 75,000/-
    for m in re.finditer(rf"{_CUR}\s*({_NUM})(?![.,]?\d)(?!\s*(?:lpa|lakhs?|lacs?|crores?|cr\b|l\b))", t):
        v = _to_float(m.group(1))
        tail = t[m.end(): m.end() + 25]
        if re.match(r"\s*(?:/-)?\s*(?:per month|p\.?m\.?|/month|monthly|a month)", tail):
            v *= 12
        out.append(int(round(v)))
    # Rupees One Lakh Fifty Thousand only
    for m in re.finditer(r"(?:rupees|rs\.?|inr)\s+((?:[a-z]+[\s-]+){1,10}?)(?:only|\)|/-|$|,|\.)", t):
        n = words_to_number(m.group(1))
        if n and n >= 1000:
            out.append(n)
    # bare grouped numbers like 1,50,000 (no currency marker) when near money words
    if not out:
        for m in re.finditer(r"\b(\d{1,2},\d{2},\d{3}|\d{2,3},\d{3})\b", t):
            out.append(int(_to_float(m.group(1))))
    return list(dict.fromkeys(out))


def normalize_duration(text: str) -> int | None:
    """First duration in `text`, in months. Handles digits, words and '(2)' style duplicates."""
    if not text:
        return None
    t = text.lower().replace("-", " ")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\([a-z\s]+\)\s*)?(years?|yrs?|months?)\b", t)
    if m:
        n = float(m.group(1))
        return int(round(n * 12)) if m.group(2).startswith("y") else int(round(n))
    m = re.search(r"\b((?:[a-z]+\s+){0,3}?)(?:\(\s*\d+\s*\)\s*)?(years?|months?)\b", t)
    if m:
        words = m.group(1)
        half = 0.5 if "and a half" in t[: m.end()] or "half" in words else 0
        n = words_to_number(words.replace("and a half", "").replace("half", ""))
        if n is not None:
            val = n + half
            return int(round(val * 12)) if m.group(2).startswith("y") else int(round(val))
    m = re.search(r"\bone and a half years?\b", t)
    if m:
        return 18
    return None


def normalize_days(text: str) -> int | None:
    """Notice period in days ('90 days', 'three months' -> 90)."""
    if not text:
        return None
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:\([a-z\s]+\)\s*)?(?:calendar\s+|working\s+)?days?\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b((?:[a-z]+\s+){1,3}?)(?:\(\s*\d+\s*\)\s*)?days?\b", t)
    if m:
        n = words_to_number(m.group(1))
        if n:
            return n
    months = normalize_duration(t)
    return months * 30 if months else None
