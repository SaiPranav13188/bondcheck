"""PII tools: detect_pii, redact, scan_for_remaining_pii.

Detection is layered:
  * pattern detectors (email, phone, PAN, Aadhaar, bank account, IFSC, IDs, DOB, pincode)
  * labelled-field and letter-structure detectors (Dear X, To-address block, Name:, Signature:)
  * name propagation: once a person's name is known, every occurrence of its parts is removed
  * optionally an LLM pass (Haiku) that lists anything the patterns missed

`scan_for_remaining_pii` runs a deliberately broader detector set than `detect_pii`, so
the Privacy Agent's re-scan is an independent check rather than the same code twice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core import llm
from core.config import settings

REDACTION = re.compile(r"\[REDACTED_[A-Z_]+\]")

# Words that look like names in letters but are not personal data.
_NOT_NAMES = {
    "sir", "madam", "candidate", "team", "hr", "human", "resources", "manager", "all", "employee", "applicant",
    "student", "trainee", "colleague", "the", "company", "management", "concerned", "whom", "it", "may",
    "concern", "congratulations", "welcome", "offer", "letter", "appointment", "dear",
}


@dataclass
class Span:
    start: int
    end: int
    type: str
    text: str

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "type": self.type, "text": self.text}


PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"(?<![\w])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?![\w])")),
    ("PHONE", re.compile(r"(?<![\w])\+91[\s-]?\d{2,4}[\s-]?\d{6,8}(?![\w])")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("BANK_ACCOUNT", re.compile(r"(?i)(?:a/?c|account)\s*(?:no\.?|number|#)?\s*[:.-]?\s*(\d[\d\s-]{7,20}\d)")),
    ("EMPLOYEE_ID", re.compile(r"(?i)(?:employee|emp|candidate|applicant|reference|ref|staff|roll)\s*"
                               r"(?:id|code|no\.?|number|#)\s*[:.-]?\s*([A-Z0-9][A-Z0-9/-]{3,})")),
    ("EMPLOYEE_ID", re.compile(r"(?i)(?:candidate|employee|emp)\s+(?:reference|ref)\s*[:.-]?\s*([A-Z0-9][A-Z0-9-]{3,})")),
    ("DOB", re.compile(r"(?i)(?:date of birth|d\.?o\.?b\.?)\s*[:.-]?\s*([0-9]{1,2}[\s/.-][0-9A-Za-z]{1,9}[\s/.-][0-9]{2,4})")),
]

_LABELLED = re.compile(
    r"(?im)^\s*(?:candidate(?:'s)?\s+name|name\s+of\s+(?:the\s+)?candidate|employee\s+name|name|"
    r"father'?s\s+name|guardian'?s\s+name|accepted\s+by|signed\s+by|signature\s+of\s+(?:the\s+)?candidate|"
    r"candidate\s+signature|signature|permanent\s+address|address|residential\s+address|"
    r"bank\s+name|account\s+holder)\s*[:\-]\s*(.+)$")

_NAME = r"[A-Z][a-zA-Z.'-]+(?:[ \t]+[A-Z][a-zA-Z.'-]+){0,3}"
_SALUTATION = re.compile(rf"(?m)\b(?:Dear|Hi|Hello)\s+(?:(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+)?({_NAME})\s*[,:]")
_HONORIFIC = re.compile(rf"\b(?:Mr|Ms|Mrs|Miss|Shri|Smt|Kumari|Dr)\.?\s+({_NAME})")
_PINCODE = re.compile(r"(?<!\d)\d{3}\s?\d{3}(?!\d)")
_HOUSE = re.compile(r"(?im)^[ \t]*((?:H\.?[ \t]?No\.?|House[ \t]+No\.?|Flat[ \t]+No\.?|D\.?[ \t]?No\.?|Door[ \t]+No\.?|"
                    r"Plot[ \t]+No\.?|Apt\.?|Apartment)[ \t]*[\w/-]+[^\n]{0,80})$")


def _pattern_spans(text: str) -> list[Span]:
    spans = []
    for typ, pat in PATTERNS:
        for m in pat.finditer(text):
            g = 1 if pat.groups else 0
            spans.append(Span(m.start(g), m.end(g), typ, m.group(g)))
    return spans


def _name_ok(name: str) -> bool:
    parts = [p.strip(".").lower() for p in name.split()]
    return bool(parts) and not all(p in _NOT_NAMES for p in parts) and len(name) >= 3


def _structure_spans(text: str) -> tuple[list[Span], set[str]]:
    """Labelled fields, salutations, honorifics and the 'To,' address block. Returns spans + person names."""
    spans: list[Span] = []
    names: set[str] = set()
    for m in _LABELLED.finditer(text):
        label = m.group(0).split(":")[0].split("-")[0].strip().lower()
        val = m.group(1).strip()
        if not val or REDACTION.fullmatch(val) or val.startswith("_") or set(val) <= {"_", " ", "."}:
            continue
        typ = "ADDRESS" if "address" in label else "SIGNATURE" if "sign" in label or "accepted" in label else \
            "BANK" if "bank" in label or "holder" in label else "NAME"
        spans.append(Span(m.start(1), m.end(1), typ, val))
        if typ in {"NAME", "SIGNATURE"} and _name_ok(val) and not re.search(r"\d", val):
            names.add(val)
    for pat in (_SALUTATION, _HONORIFIC):
        for m in pat.finditer(text):
            n = m.group(1).strip()
            if _name_ok(n):
                spans.append(Span(m.start(1), m.end(1), "NAME", n))
                names.add(n)
    # Signatory: a short capitalised line right above a job title, or right below a sign-off.
    for m in re.finditer(r"(?m)^[ \t]*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})[ \t]*\n[ \t]*(?=[^\n]*(?:Manager|Head|"
                         r"Human Resources|HR\b|Talent|Signatory|People|Recruit|Director|Officer))", text):
        n = m.group(1)
        if _name_ok(n):
            spans.append(Span(m.start(1), m.end(1), "NAME", n))
    for m in re.finditer(r"(?im)^[ \t]*(?:warm regards|regards|yours sincerely|yours faithfully|sincerely|"
                         r"authori[sz]ed signatory)[ ,]*\n[ \t]*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})[ \t]*$", text):
        if _name_ok(m.group(1)):
            spans.append(Span(m.start(1), m.end(1), "NAME", m.group(1)))
    # "To,\n<Name>\n<address lines>\n\n" block at the top of most Indian offer letters.
    # Parsed line by line because PDF text extraction often drops the blank line that ends the block.
    m = re.search(r"(?im)^[ \t]*To,?[ \t]*\n", text)
    if m:
        offset = m.end()
        for i, line in enumerate(text[offset:].split("\n")[:6]):
            stripped = line.strip()
            if not stripped or re.match(r"(?i)(subject|sub\b|dear|ref\b|date\b|re:)", stripped) or (
                    i > 0 and re.match(r"^[A-Z][\w .'/()-]{1,30}:\s", stripped)):
                break
            if not REDACTION.fullmatch(stripped):
                s = offset + line.index(stripped)
                typ = "NAME" if i == 0 else "ADDRESS"
                spans.append(Span(s, s + len(stripped), typ, stripped))
                if i == 0 and _name_ok(stripped):
                    names.add(re.sub(r"^(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+", "", stripped))
            offset += len(line) + 1
    # House / flat / door number lines anywhere.
    for m in _HOUSE.finditer(text):
        spans.append(Span(m.start(1), m.end(1), "ADDRESS", m.group(1)))
    return spans, names


def _propagate_names(text: str, names: set[str]) -> list[Span]:
    """Every occurrence of a known person's full name or its parts (first name in 'Dear Rahul,')."""
    spans = []
    tokens = set()
    for n in names:
        tokens.add(n)
        tokens.update(p for p in re.split(r"\s+", n) if len(p.strip(".")) > 2 and p.lower().strip(".") not in _NOT_NAMES)
    for tok in sorted(tokens, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w]){re.escape(tok)}(?![\w])", text):
            spans.append(Span(m.start(), m.end(), "NAME", m.group(0)))
    return spans


def _llm_spans(text: str, meter: llm.TokenMeter | None) -> list[Span]:
    if settings.offline:
        return []
    out = llm.json_call(
        model=settings.fast_model,
        system="You find personal information in offer letters so it can be redacted. " + llm.DATA_ONLY_RULE,
        prompt="List every exact substring of the text below that identifies the candidate or another private "
               "person: names, addresses, phone numbers, emails, IDs (PAN, Aadhaar, employee/candidate IDs), "
               "dates of birth, bank details, signatures. Do NOT list company names, company addresses, HR "
               "department names or generic job titles. Already-redacted tokens like [REDACTED_NAME] are fine.\n\n"
               f"<document>\n{text[:30000]}\n</document>",
        schema={"type": "object", "additionalProperties": False, "required": ["items"],
                "properties": {"items": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["text", "type"],
                    "properties": {"text": {"type": "string"}, "type": {"type": "string"}}}}}},
        meter=meter, max_tokens=3000,
    )
    spans = []
    for item in out.get("items", []):
        s = (item.get("text") or "").strip()
        if len(s) < 3 or REDACTION.fullmatch(s):
            continue
        typ = re.sub(r"[^A-Z_]", "", (item.get("type") or "PII").upper().replace(" ", "_")) or "PII"
        for m in re.finditer(re.escape(s), text):
            spans.append(Span(m.start(), m.end(), typ, s))
    return spans


def _inside_redaction(text: str, span: Span) -> bool:
    for m in REDACTION.finditer(text):
        if m.start() <= span.start and span.end <= m.end():
            return True
    return False


def detect_pii(text: str, meter: llm.TokenMeter | None = None, use_llm: bool = True) -> list[dict]:
    spans = _pattern_spans(text)
    struct, names = _structure_spans(text)
    spans += struct + _propagate_names(text, names)
    if use_llm:
        spans += _llm_spans(text, meter)
    return [s.as_dict() for s in spans if not _inside_redaction(text, s)]


def redact(text: str, spans: list[dict]) -> str:
    """Replace spans with [REDACTED_<TYPE>] tokens (overlapping spans are merged)."""
    if not spans:
        return text
    ordered = sorted(spans, key=lambda s: (s["start"], -s["end"]))
    merged: list[dict] = []
    for s in ordered:
        if merged and s["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
        else:
            merged.append(dict(s))
    out = text
    for s in reversed(merged):
        out = out[: s["start"]] + f"[REDACTED_{s['type']}]" + out[s["end"]:]
    return out


def scan_for_remaining_pii(text: str, meter: llm.TokenMeter | None = None, use_llm: bool = True) -> list[dict]:
    """Independent re-scan of redacted text with broader rules than detect_pii."""
    found = detect_pii(text, meter=None, use_llm=False)
    # Broader rules: any long digit run, any pincode, any line next to a redacted name/address.
    for m in re.finditer(r"(?<![\w.,])\d{9,18}(?![\w])", text):
        found.append(Span(m.start(), m.end(), "NUMBER", m.group(0)).as_dict())
    # ID-like tokens (NX38977, EMP10429) on a line that already held personal data.
    for line_m in re.finditer(r"(?m)^.*\[REDACTED_[A-Z_]+\].*$", text):
        for m in re.finditer(r"\b[A-Z]{1,4}\d{4,8}\b", line_m.group(0)):
            s = line_m.start() + m.start()
            found.append(Span(s, s + len(m.group(0)), "EMPLOYEE_ID", m.group(0)).as_dict())
    for m in _PINCODE.finditer(text):
        ctx = text[max(0, m.start() - 80): m.start()]
        if "[REDACTED_ADDRESS]" in ctx or re.search(r"(?i)pin|address|road|nagar|street|colony|district", ctx):
            found.append(Span(m.start(), m.end(), "ADDRESS", m.group(0)).as_dict())
    for m in re.finditer(r"(?m)^(\[REDACTED_(?:NAME|ADDRESS)\][^\n]*\n)([^\n\[]{3,80})$", text):
        line = m.group(2).strip()
        if re.search(r"\d{3}\s?\d{3}|road|street|nagar|colony|lane|sector|district|flat|house|apartment|"
                     r"[A-Z][a-z]+,\s*[A-Z][a-z]+", line, re.I) and not re.search(r"(?i)subject|dear|date", line):
            s = m.start(2) + m.group(2).index(line)
            found.append(Span(s, s + len(line), "ADDRESS", line).as_dict())
    if use_llm:
        found += [s.as_dict() for s in _llm_spans(text, meter) if not _inside_redaction(text, s)]
    return [f for f in found if not REDACTION.fullmatch(f["text"].strip())]
