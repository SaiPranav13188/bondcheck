"""Extraction Agent. Goal: a structured, evidence-backed record of the offer terms.

Self-verification loop (the core agentic behaviour):
  1. Extract every field with an evidence quote.
  2. verify_quote() each quote against the document (catches made-up values).
  3. Check the value really follows from the quote (normalize_amount / normalize_duration)
     and that the quote is about the right thing (a probation clause is not a bond clause).
  4. On failure, re-read just that section with feedback and try again (max 2 re-reads).
  5. Score confidence; ask the uploader about anything still uncertain.

Two interchangeable engines produce candidates: Claude (when an API key is set) and a
deterministic rule engine (offline). The verification loop is the same for both.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from core import llm
from core.config import settings
from core.runlog import RunContext
from tools.documents import SECTION_KEYWORDS, read_section, split_clauses, verify_quote
from tools.normalize import normalize_amount, normalize_days, normalize_duration

# field -> (type, section, description)
FIELDS: dict[str, tuple[str, str, str]] = {
    "company_name": ("string", "company", "Legal name of the employer"),
    "batch_year": ("integer", "batch", "Graduating batch / year of joining, e.g. 2026"),
    "role": ("string", "role", "Job title / designation offered"),
    "ctc_annual": ("integer", "compensation", "Annual CTC in rupees (convert LPA or monthly figures)"),
    "has_bond": ("boolean", "bond", "Whether the candidate must serve a minimum period or pay a penalty"),
    "bond_months": ("integer", "bond", "Length of the bond / minimum service commitment in months"),
    "penalty_amount": ("integer", "penalty", "Rupee amount payable for leaving before the bond ends"),
    "penalty_prorated": ("enum", "prorated", "yes if reduced for time served, no if full amount always, "
                                             "not_mentioned otherwise"),
    "notice_days": ("integer", "notice", "Notice period in days after confirmation"),
    "training_cost_recovery": ("boolean", "training", "Whether training costs are recovered if the employee leaves"),
    "certificates_retained": ("boolean", "certificates", "Whether original certificates are kept by the employer"),
    "other_risky_clauses": ("list", "risky", "Other clauses that are risky for a fresher, as short phrases"),
}
KEY_FIELDS = {"company_name", "has_bond", "bond_months", "penalty_amount"}

# Words the quote must contain to be about the right thing, and words that indicate a mix-up.
RELEVANCE: dict[str, tuple[list[str], list[str]]] = {
    "bond_months": (SECTION_KEYWORDS["bond"] + ["serve", "service"], ["probation", "notice period", "training period"]),
    "penalty_amount": (SECTION_KEYWORDS["penalty"] + ["bond"], ["ctc", "cost to company", "per annum", "salary of",
                                                                 "stipend", "remuneration"]),
    "ctc_annual": (SECTION_KEYWORDS["compensation"], ["liquidated", "penalty", "damages", "bond amount", "stipend",
                                                       "during training"]),
    "notice_days": (["notice", "resign", "relieving", "termination", "separation"], ["accept", "joining", "report"]),
    "has_bond": (SECTION_KEYWORDS["bond"] + ["serve"], []),
    "training_cost_recovery": (["training"], []),
    "certificates_retained": (["certificate", "original documents", "mark sheet", "marksheet"], []),
}

_SENT_SPLIT = re.compile(r"(?<!\bRs\.)(?<!\bNo\.)(?<!\bPvt\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)"
                         r"(?<=[.;])\s+(?=[A-Z(\"])")


_KEY_LINE = re.compile(r"^\s*[A-Z][\w ()/&'.-]{1,45}:\s*\S")
NEGATIONS = ["no bond", "not bound", "no service agreement", "does not require", "not require you", "not applicable",
             "no service commitment", "not required to sign", "without any bond", "no minimum service"]
RETAIN_WORDS = ["retain", "custody", "deposit", "kept", "held", "surrender"]


def _units(clause: str) -> list[str]:
    """Split table-like 'Key: value' lines apart; re-join wrapped prose lines."""
    units: list[str] = []
    prev_key = False
    for line in clause.split("\n"):
        is_key = bool(_KEY_LINE.match(line))
        if not units or is_key or prev_key:
            units.append(line.strip())
        else:
            units[-1] = f"{units[-1]} {line.strip()}"
        prev_key = is_key
    return units


def sentences(text: str) -> list[str]:
    out = []
    for clause in split_clauses(text):
        for unit in _units(clause):
            for s in _SENT_SPLIT.split(unit):
                s = s.strip()
                if len(s) > 3:
                    out.append(s)
    return out


def _has(s: str, words: list[str]) -> bool:
    low = s.lower()
    return any(w in low for w in words)


def _fv(value: Any, quote: str = "", confidence: float = 0.9, source: str = "extracted") -> dict:
    return {"value": value, "quote": quote, "confidence": confidence, "source": source, "checks": []}


# =========================================================================== rule engine (offline)

_CO_RE = re.compile(r"\b((?:[A-Z][A-Za-z0-9&]+\s+){1,4}?(?:Private|Pvt\.?)\s+(?:Limited|Ltd\.?))")
_CO_RE2 = re.compile(r"\b((?:[A-Z][A-Za-z0-9&]+\s+){0,3}(?:Technologies|Technology|Solutions|Systems|Infotech|Software|"
                     r"Labs|Consulting|Services|Analytics|Networks|Digital|Studios)(?:\s+(?:LLP|Limited|Ltd\.?|Inc\.?))?)")
_ROLE_RE = [
    re.compile(r"(?i)(?:designation|position|role|post)\s*[:\-]\s*([A-Z][A-Za-z /&()-]{3,60}?)\s*(?:\n|$|,|\.(?:\s|$))"),
    re.compile(r"(?:position|post|role) of\s+(?:an?\s+)?[\"“]?([A-Z][A-Za-z /&-]{3,60}?)[\"”]?(?=\s+(?:at|with|in|on|for|"
               r"and|effective|w\.e\.f)\b|[,.(])"),
    re.compile(r"(?:appointed|appoint you|join(?:ing)?|selected|offer you employment|appointment)\s+as\s+(?:an?\s+)?"
               r"[\"“]?([A-Z][A-Za-z /&-]{3,60}?)"
               r"[\"”]?(?=\s+(?:at|with|in|on|for|and|effective|w\.e\.f)\b|[,.(])"),
]


class RuleEngine:
    """Deterministic extractor. `first_pass` scans the whole letter and takes the first plausible
    match (fast but easily fooled); `reread` looks only at the relevant section with stricter rules."""

    name = "rule-engine"

    def __init__(self, batch_year_hint: int | None = None):
        self.batch_year_hint = batch_year_hint

    # ---- first pass: whole document, first plausible match
    def first_pass(self, text: str, ctx: RunContext | None = None) -> dict[str, dict]:
        sents = sentences(text)
        out: dict[str, dict] = {}
        out["company_name"] = self._company(text)
        out["role"] = self._role(text)
        out["batch_year"] = self._batch(text, sents)
        out["ctc_annual"] = self._first_amount(sents, ["ctc", "salary", "package", "remuneration", "stipend",
                                                       "compensation", "per annum", "lpa"])
        bond_sent = next((s for s in sents if _has(s, SECTION_KEYWORDS["bond"])), None)
        out["has_bond"] = _fv(True, bond_sent, 0.9) if bond_sent else _fv(False, "", 0.8, "default")
        out["bond_months"] = self._first_duration(sents, ["serve", "service", "period", "bond", "commitment"])
        out["penalty_amount"] = self._first_amount(sents, ["pay", "amount", "damages", "penalty", "recover",
                                                           "compensate"])
        out["penalty_prorated"] = self._prorated(sents)
        out["notice_days"] = self._first_days(sents)
        out["training_cost_recovery"] = self._bool_clause(sents, ["training"], ["cost", "expense", "recover", "fee",
                                                                               "reimburse", "pay"])
        out["certificates_retained"] = self._bool_clause(sents, ["original"], ["certificate", "mark sheet", "marksheet",
                                                                              "documents"])
        out["other_risky_clauses"] = self._risky(sents)
        return out

    # ---- re-read: one field, one section, stricter rules
    def reread(self, field: str, section_text: str, full_text: str, feedback: str) -> dict:
        sents = sentences(section_text) or sentences(full_text)
        if field == "bond_months":
            for s in sents:
                if _has(s, SECTION_KEYWORDS["bond"] + ["serve the company", "serve"]) and not _has(s, ["probation"]):
                    d = normalize_duration(s)
                    if d:
                        return _fv(d, s, 0.85, "reread")
            return _fv(None, "", 0.3, "reread")
        if field == "penalty_amount":
            for s in sents:
                if _has(s, SECTION_KEYWORDS["penalty"]) and not _has(s, RELEVANCE["penalty_amount"][1]):
                    amts = [a for a in normalize_amount(s) if a >= 5000]
                    if amts:
                        return _fv(max(amts), s, 0.85, "reread")
            return _fv(None, "", 0.3, "reread")
        if field == "ctc_annual":
            ranked = sorted(sents, key=lambda s: (not _has(s, ["ctc", "cost to company", "per annum", "lpa"]),
                                                  _has(s, ["stipend", "during training"])))
            for s in ranked:
                if _has(s, SECTION_KEYWORDS["compensation"]) and not _has(s, RELEVANCE["ctc_annual"][1]):
                    amts = [a for a in normalize_amount(s) if a >= 60000]
                    if amts:
                        return _fv(max(amts), s, 0.85, "reread")
            return _fv(None, "", 0.3, "reread")
        if field == "notice_days":
            for s in sents:
                if _has(s, ["notice"]) and not _has(s, ["accept", "joining"]):
                    d = normalize_days(s)
                    if d:
                        return _fv(d, s, 0.85, "reread")
            return _fv(None, "", 0.5, "reread")
        if field == "certificates_retained":
            for s in sents:
                if _has(s, ["certificate", "documents", "mark sheet"]) and _has(s, ["original"]):
                    retained = _has(s, ["retain", "custody", "deposit", "kept", "held", "submit and", "surrender"]) \
                        and not _has(s, ["returned immediately", "verification only", "will be returned after verification",
                                         "will not retain", "not be retained", "does not retain"])
                    return _fv(retained, s, 0.85, "reread")
            return _fv(False, "", 0.8, "default")
        if field == "has_bond":
            if any(_has(s, NEGATIONS) for s in sentences(full_text)):
                neg = next(s for s in sentences(full_text) if _has(s, NEGATIONS))
                return _fv(False, neg, 0.9, "reread")
            s = next((s for s in sents if _has(s, SECTION_KEYWORDS["bond"])), None)
            return _fv(True, s, 0.85, "reread") if s else _fv(False, "", 0.8, "default")
        if field == "company_name":
            return self._company(full_text, strict=True)
        if field == "role":
            return self._role(full_text)
        if field == "batch_year":
            return self._batch(full_text, sentences(full_text))
        if field == "training_cost_recovery":
            return self._bool_clause(sents, ["training"], ["recover", "reimburse", "pay", "refund", "deduct"])
        return _fv(None, "", 0.3, "reread")

    # ---- helpers
    def _company(self, text: str, strict: bool = False) -> dict:
        for pat in (_CO_RE, _CO_RE2):
            for m in pat.finditer(text):
                name = re.sub(r"\s+", " ", m.group(1)).strip()
                if strict and len(name.split()) < 2:
                    continue
                if name.split()[0].lower() in {"the", "our", "this", "your", "a", "in", "at", "of", "dear", "for"}:
                    name = " ".join(name.split()[1:])
                if len(name) > 4:
                    line = next((ln.strip() for ln in text.splitlines() if m.group(1).split()[0] in ln and
                                 name.split()[-1].rstrip(".") in ln), name)
                    return _fv(name, line, 0.9)
        return _fv(None, "", 0.2)

    def _role(self, text: str) -> dict:
        sents = sentences(text)  # wrapped PDF lines re-joined
        for pat in _ROLE_RE:
            for s in sents:
                m = pat.search(s)
                if m:
                    role = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
                    return _fv(role, s, 0.85)
        return _fv(None, "", 0.4)

    def _batch(self, text: str, sents: list[str]) -> dict:
        for pat in (r"(?i)\b(20\d{2})\s+(?:batch|pass(?:ing)?[- ]out|campus)", r"(?i)batch\s*(?:of|:)?\s*(20\d{2})",
                    r"(?i)class of\s*(20\d{2})"):
            m = re.search(pat, text)
            if m:
                phrase = re.sub(r"\s+", " ", m.group(0)).lower()
                s = next((s for s in sents if phrase in re.sub(r"\s+", " ", s).lower()),
                         next((s for s in sents if m.group(1) in s), m.group(0)))
                return _fv(int(m.group(1)), s, 0.9)
        m = re.search(r"(?i)(?:date of joining|joining date|join(?:ing)? on|report on)[^\n]{0,40}?(20\d{2})", text)
        if m:
            s = next((s for s in sents if m.group(1) in s and _has(s, ["join", "report"])), m.group(0))
            return _fv(int(m.group(1)), s, 0.75)
        if self.batch_year_hint:
            return _fv(self.batch_year_hint, "", 0.8, "uploader_hint")
        m = re.search(r"\b(20[2-3]\d)\b", text)
        if m:
            s = next((s for s in sents if m.group(1) in s), m.group(0))
            return _fv(int(m.group(1)), s, 0.6)
        return _fv(date.today().year, "", 0.4, "default")

    def _first_amount(self, sents: list[str], words: list[str]) -> dict:
        for s in sents:
            if _has(s, words):
                amts = [a for a in normalize_amount(s) if a >= 5000]
                if amts:
                    return _fv(amts[0], s, 0.9)
        return _fv(None, "", 0.5)

    def _first_duration(self, sents: list[str], words: list[str]) -> dict:
        for s in sents:
            if _has(s, words):
                d = normalize_duration(s)
                if d:
                    return _fv(d, s, 0.9)
        return _fv(None, "", 0.5)

    def _first_days(self, sents: list[str]) -> dict:
        for s in sents:
            m = re.search(r"\d+\s*(?:\([a-z\s]+\)\s*)?days?", s, re.I)
            if m:
                return _fv(int(re.match(r"\d+", m.group(0)).group(0)), s, 0.9)
            if _has(s, ["notice"]):
                d = normalize_days(s)
                if d:
                    return _fv(d, s, 0.9)
        return _fv(None, "", 0.5)

    def _prorated(self, sents: list[str]) -> dict:
        for s in sents:
            if _has(s, SECTION_KEYWORDS["prorated"]) and not _has(s, ["not be pro", "not pro-rat", "no pro-rat"]):
                return _fv("yes", s, 0.9)
        for s in sents:
            if _has(s, SECTION_KEYWORDS["penalty"] + ["amount", "payable"]) and _has(
                    s, ["irrespective of", "regardless of", "in full", "full amount", "entire amount", "not be pro",
                        "not pro-rat", "no pro-rat", "whole amount"]):
                return _fv("no", s, 0.9)
        return _fv("not_mentioned", "", 0.85, "default")

    def _bool_clause(self, sents: list[str], must: list[str], also: list[str]) -> dict:
        for s in sents:
            if _has(s, must) and _has(s, also):
                return _fv(True, s, 0.85)
        return _fv(False, "", 0.8, "default")

    _RISKS = [
        ("salary withheld during probation", ["withheld", "withhold"], ["salary", "pay", "stipend"]),
        ("salary forfeited on early exit", ["forfeit"], ["salary", "pay", "bonus", "variable"]),
        ("non-compete clause", ["non-compete", "non compete", "shall not join", "not join any competitor"], []),
        ("blank cheques or surety required", ["blank cheque", "post-dated cheque", "postdated cheque", "surety",
                                              "guarantor", "security cheque"], []),
        ("can be relocated anywhere", ["any location", "anywhere in india", "any of its offices", "any office"],
         ["transfer", "posted", "relocat", "deploy"]),
        ("termination without notice during probation", ["without notice", "without any notice"], ["terminat"]),
        ("salary deducted for training", ["deduct"], ["training"]),
    ]

    def _risky(self, sents: list[str]) -> dict:
        found, quotes = [], []
        for label, kws, ctx_words in self._RISKS:
            for s in sents:
                if _has(s, kws) and (not ctx_words or _has(s, ctx_words)):
                    found.append(label)
                    quotes.append(s)
                    break
        fv = _fv(found, quotes[0] if quotes else "", 0.85 if found else 0.8, "extracted" if found else "default")
        fv["quotes"] = quotes
        return fv


# =========================================================================== Claude engine

def _schema_for(ftype: str) -> dict:
    return {
        "string": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "integer": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "boolean": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "enum": {"type": "string", "enum": ["yes", "no", "not_mentioned"]},
        "list": {"type": "array", "items": {"type": "string"}},
    }[ftype]


def _field_schema(ftype: str) -> dict:
    props = {"value": _schema_for(ftype), "quote": {"type": "string"}, "confidence": {"type": "number"}}
    req = ["value", "quote", "confidence"]
    if ftype == "list":
        props["quotes"] = {"type": "array", "items": {"type": "string"}}
        req.append("quotes")
    return {"type": "object", "additionalProperties": False, "required": req, "properties": props}


EXTRACTION_SYSTEM = (
    "You extract job-offer terms from Indian offer letters and service agreements for a student transparency "
    "database. For each field give the value, an evidence quote copied VERBATIM from the document (one short "
    "sentence or clause, exactly as written, including [REDACTED_...] tokens), and your confidence from 0 to 1. "
    "If a field is not stated, use null (or 'not_mentioned' / an empty list) with an empty quote. "
    "Never infer or invent values that the text does not state. Convert amounts to plain rupee integers "
    "(1.5 lakh -> 150000; 'Rs 40,000 per month' CTC -> 480000) and durations to months / notice to days. "
    "A probation period, training period or notice period is NOT the bond period. A salary is NOT a penalty. "
    + llm.DATA_ONLY_RULE
)


class ClaudeEngine:
    name = "claude"

    def __init__(self, meter: llm.TokenMeter, batch_year_hint: int | None = None):
        self.meter = meter
        self.batch_year_hint = batch_year_hint

    def first_pass(self, text: str, ctx: RunContext | None = None) -> dict[str, dict]:
        schema = {"type": "object", "additionalProperties": False, "required": list(FIELDS),
                  "properties": {f: _field_schema(t) for f, (t, _, _) in FIELDS.items()}}
        fields_doc = "\n".join(f"- {f}: {d}" for f, (_, _, d) in FIELDS.items())
        hint = f"\nThe uploader says their batch is {self.batch_year_hint}." if self.batch_year_hint else ""
        out = llm.json_call(model=settings.strong_model, system=EXTRACTION_SYSTEM, meter=self.meter, schema=schema,
                            prompt=f"Fields:\n{fields_doc}{hint}\n\n<document>\n{text[:60000]}\n</document>",
                            effort="medium")
        return {f: {**out[f], "source": "extracted", "checks": []} for f in FIELDS}

    def reread(self, field: str, section_text: str, full_text: str, feedback: str) -> dict:
        ftype, _, desc = FIELDS[field]
        out = llm.json_call(
            model=settings.strong_model, system=EXTRACTION_SYSTEM, meter=self.meter, schema=_field_schema(ftype),
            prompt=f"Re-read the section below and extract only `{field}` ({desc}).\n"
                   f"Your previous answer failed a check: {feedback}\n"
                   f"Copy the quote exactly from this section. If the section does not state it, return null.\n\n"
                   f"<section>\n{section_text or full_text[:20000]}\n</section>",
            effort="medium")
        return {**out, "source": "reread", "checks": []}


# =========================================================================== verification

def check_field(field: str, fv: dict, text: str) -> list[str]:
    """Problems with one extracted field. Empty list = passed every check."""
    problems: list[str] = []
    value, quote = fv.get("value"), (fv.get("quote") or "").strip()
    if value is None or value == [] or fv.get("source") in {"default", "uploader_hint"}:
        return problems
    if field == "has_bond" and value is False:
        return problems
    if field == "penalty_prorated" and value == "not_mentioned":
        return problems
    quotes = fv.get("quotes") or [quote]
    for q in quotes:
        vq = verify_quote(q, text)
        if not vq["found"]:
            problems.append(f"quote_not_found: the quote '{q[:80]}' does not appear in the document")
            return problems
    if field in {"ctc_annual", "penalty_amount"}:
        amts = normalize_amount(quote)
        if amts and not any(abs(a - value) <= max(1, 0.01 * value) for a in amts):
            problems.append(f"value_mismatch: {value} does not match the amounts in the quote ({amts})")
        elif not amts:
            problems.append("value_mismatch: the quote contains no rupee amount")
    elif field == "bond_months":
        d = normalize_duration(quote)
        n_durations = len(set(re.findall(r"\d+\s*(?:\([a-z\s-]+\)\s*)?(?:months?|years?)", quote.lower())))
        if d != value:
            problems.append(f"value_mismatch: {value} months does not match the quote ({d})")
        elif n_durations > 1:
            problems.append("ambiguous_quote: the quote mentions several periods; re-read the bond clause alone")
    elif field == "has_bond" and value is True:
        if _has(quote, NEGATIONS):
            problems.append("negated: the quote says there is NO bond")
    elif field == "certificates_retained" and value is True:
        if not _has(quote, RETAIN_WORDS) or _has(quote, ["returned immediately", "returned after", "will be returned"]):
            problems.append("mixup: the quote is about checking certificates, not keeping them")
    elif field == "training_cost_recovery" and value is True:
        if not _has(quote, ["recover", "reimburse", "refund", "deduct", "pay", "liable"]):
            problems.append("mixup: the quote mentions training but not recovering its cost")
    elif field == "notice_days":
        d = normalize_days(quote)
        if d is not None and d != value:
            problems.append(f"value_mismatch: {value} days does not match the quote ({d})")
    elif field == "batch_year":
        if str(value) not in quote:
            problems.append("value_mismatch: the year is not in the quote")
    elif field == "company_name":
        first = re.sub(r"[^a-z0-9]", "", str(value).split()[0].lower())
        if first and first not in re.sub(r"[^a-z0-9]", "", quote.lower()):
            problems.append("value_mismatch: the company name is not in the quote")
    if field in RELEVANCE:
        must, mixups = RELEVANCE[field]
        if must and not _has(quote, must):
            problems.append(f"irrelevant_quote: the quote is not about {field.replace('_', ' ')}")
        elif mixups and _has(quote, mixups) and not (
                (field == "bond_months" and _has(quote, ["bond", "service agreement"]))
                or (field == "ctc_annual" and _has(quote, ["ctc", "cost to company"]) and not _has(quote, ["stipend"]))):
            problems.append(f"mixup: the quote looks like a different clause ({', '.join(w for w in mixups if w in quote.lower())})")
    return problems


def cross_checks(fields: dict[str, dict]) -> dict[str, str]:
    """Consistency between fields -> {field: problem}."""
    issues = {}
    hb = fields["has_bond"].get("value")
    if hb and fields["bond_months"].get("value") is None and fields["penalty_amount"].get("value") is None:
        issues["has_bond"] = "inconsistent: a bond was found but neither a bond period nor a penalty; re-check"
    if hb and fields["bond_months"].get("value") is None:
        issues["bond_months"] = "inconsistent: the letter has a bond but no bond period was found"
    if hb and fields["penalty_amount"].get("value") is None:
        issues["penalty_amount"] = "inconsistent: the letter has a bond but no penalty amount was found"
    if not hb and (fields["penalty_amount"].get("value") or fields["bond_months"].get("value")):
        issues["has_bond"] = "inconsistent: a bond period or penalty was found but has_bond is false"
    ctc, pen = fields["ctc_annual"].get("value"), fields["penalty_amount"].get("value")
    if ctc and pen and pen == ctc and fields["ctc_annual"].get("quote") == fields["penalty_amount"].get("quote"):
        issues["penalty_amount"] = "inconsistent: the penalty was read from the salary clause"
    return issues


# =========================================================================== agent

QUESTION_TEMPLATES = {
    "company_name": "We read the company as “{v}”. Is that correct?",
    "batch_year": "We read your batch as {v}. Is that correct?",
    "role": "We read the role as “{v}”. Is that correct?",
    "ctc_annual": "We read the annual CTC as {v}. Is that correct?",
    "has_bond": "We read that this letter {v} a bond. Is that correct?",
    "bond_months": "We read the bond as {v} months. Is that correct?",
    "penalty_amount": "We read the bond penalty as {v}. Is that correct?",
    "penalty_prorated": "We read the penalty as {v}. Is that correct?",
    "notice_days": "We read the notice period as {v} days. Is that correct?",
    "training_cost_recovery": "We read that training costs {v} recovered if you leave. Is that correct?",
    "certificates_retained": "We read that original certificates {v} kept by the company. Is that correct?",
}
MISSING_TEMPLATES = {
    "company_name": "We couldn't find the company name. What is it?",
    "bond_months": "We couldn't find how long the bond lasts. How many months does your letter say?",
    "penalty_amount": "We couldn't find the bond penalty. What amount does your letter say (in ₹)?",
    "has_bond": "Does your letter require you to stay for a minimum period or pay a penalty?",
}


def _display(field: str, v: Any) -> str:
    from tools.calculator import inr

    if field in {"ctc_annual", "penalty_amount"}:
        return inr(v)
    if field == "has_bond":
        return "includes" if v else "does not include"
    if field == "training_cost_recovery":
        return "are" if v else "are not"
    if field == "certificates_retained":
        return "are" if v else "are not"
    if field == "penalty_prorated":
        return {"yes": "reduced for time served (pro-rated)", "no": "the full amount regardless of time served",
                "not_mentioned": "not mentioned as pro-rated"}[v]
    return str(v)


def make_engine(meter: llm.TokenMeter, batch_year_hint: int | None = None):
    return RuleEngine(batch_year_hint) if settings.offline else ClaudeEngine(meter, batch_year_hint)


def single_pass(text: str, engine) -> dict[str, dict]:
    """Baseline for the evaluation: one extraction, no checks, no re-reads."""
    return engine.first_pass(text)


def run(text: str, ctx: RunContext, batch_year_hint: int | None = None, engine=None) -> tuple[dict, list[str], list[dict]]:
    """Returns (fields, needs_user_confirmation, questions)."""
    engine = engine or make_engine(ctx.meter, batch_year_hint)
    A = "Extraction Agent"
    with ctx.agent(A):
        ctx.emit(A, "tool", f"Extracting {len(FIELDS)} fields with evidence quotes ({engine.name})")
        fields = engine.first_pass(text, ctx)
        ctx.emit(A, "info", "First pass complete", values={f: v.get("value") for f, v in fields.items()})

        for rnd in range(settings.extraction_max_rereads + 1):
            problems = {f: check_field(f, fv, text) for f, fv in fields.items()}
            for f, p in cross_checks(fields).items():
                problems.setdefault(f, []).append(p)
            failing = {f: p for f, p in problems.items() if p}
            passed = [f for f in FIELDS if f not in failing and fields[f].get("value") not in (None, [])]
            ctx.emit(A, "check", f"verify_quote + value checks: {len(passed)} passed, {len(failing)} failed"
                     + (f" ({', '.join(failing)})" if failing else ""),
                     failing={f: p[0] for f, p in failing.items()})
            for f, p in problems.items():
                fields[f]["checks"] = p
            if not failing or rnd == settings.extraction_max_rereads:
                break
            for f, p in failing.items():
                section = FIELDS[f][1]
                section_text = read_section(text, section)
                ctx.emit(A, "retry", f"Re-reading the {section} section for {f}: {p[0].split(':')[0]}", field=f)
                new = engine.reread(f, section_text, text, "; ".join(p))
                new_problems = check_field(f, new, text)
                old_problems = p
                if not new_problems or len(new_problems) < len(old_problems) or new.get("value") != fields[f].get("value"):
                    fields[f] = new
                    ctx.emit(A, "info", f"{f}: {fields[f].get('value')!r} after re-read", field=f)

        # Confidence scoring and the "no unsupported values" rule.
        for f, fv in fields.items():
            base = float(fv.get("confidence") or 0.5)
            checks = fv.get("checks") or []
            if any(c.startswith("quote_not_found") for c in checks):
                ctx.emit(A, "decision", f"{f}: dropped {fv.get('value')!r} because its quote could not be found")
                fv["value"] = None if f != "other_risky_clauses" else []
                fv["quote"] = ""
                fv["confidence"] = 0.0
            elif checks:
                fv["confidence"] = round(min(base, 0.55), 2)
            else:
                fv["confidence"] = round(min(base, 0.98), 2)

        needs = []
        questions = []
        has_bond = fields["has_bond"].get("value")
        for f in FIELDS:
            fv = fields[f]
            if f == "other_risky_clauses":
                continue
            relevant = f in KEY_FIELDS and (has_bond or f in {"company_name", "has_bond"})
            if fv.get("value") is None and relevant:
                needs.append(f)
                questions.append({"field": f, "question": MISSING_TEMPLATES.get(f, f"What does your letter say about {f}?"),
                                  "current": None, "type": FIELDS[f][0]})
            elif fv.get("value") is not None and fv["confidence"] < settings.confidence_threshold:
                needs.append(f)
                questions.append({"field": f, "question": QUESTION_TEMPLATES[f].format(v=_display(f, fv["value"])),
                                  "current": fv["value"], "quote": fv.get("quote"), "type": FIELDS[f][0]})
        if needs:
            ctx.emit(A, "ask", f"{len(needs)} field(s) below the confidence threshold; asking the uploader",
                     fields=needs)
        else:
            ctx.emit(A, "done", "All fields verified against the document")
        return fields, needs, questions


def apply_answers(fields: dict, questions: list[dict], answers: dict) -> dict:
    """Uploader replies: {'field': 'yes'} confirms; any other value is a correction."""
    from tools.normalize import normalize_amount as na

    for q in questions:
        f = q["field"]
        ans = answers.get(f)
        if ans is None:
            continue
        fv = fields[f]
        if isinstance(ans, str) and ans.strip().lower() in {"yes", "correct", "y", "confirm"}:
            fv["confidence"] = max(fv.get("confidence", 0), 0.9)
            fv["source"] = "uploader_confirmed"
            continue
        if isinstance(ans, str) and ans.strip().lower() in {"no", "incorrect", "wrong"}:
            if FIELDS[f][0] == "boolean" and fv.get("value") is not None:
                fv.update(value=not fv["value"], confidence=0.85, source="uploader_corrected")
            else:  # rejected without a correction: we don't store a value we can't support
                fv.update(value=None, confidence=0.0, source="uploader_rejected")
            continue
        if isinstance(ans, str) and ans.strip().lower() in {"not in letter", "not mentioned", "none", "no bond"}:
            if f == "has_bond":
                fv.update(value=False, confidence=0.9, source="uploader_corrected")
            else:
                fv.update(value=None, confidence=0.9, source="uploader_corrected")
            continue
        ftype = FIELDS[f][0]
        value: Any = ans
        if ftype == "integer" and isinstance(ans, str):
            if f in {"ctc_annual", "penalty_amount"}:
                amts = na(ans if re.search(r"(?i)rs|₹|inr|lakh|lpa", ans) else f"Rs. {ans}")
                value = amts[0] if amts else None
            elif f == "bond_months":
                value = normalize_duration(ans) or (int(re.sub(r"\D", "", ans)) if re.search(r"\d", ans) else None)
            else:
                value = int(re.sub(r"\D", "", ans)) if re.search(r"\d", ans) else None
        elif ftype == "boolean" and isinstance(ans, str):
            value = ans.strip().lower() in {"true", "yes", "y", "has bond", "it does"}
        fv.update(value=value, confidence=0.85, source="uploader_corrected")
    if fields["bond_months"].get("value") or fields["penalty_amount"].get("value"):
        if fields["has_bond"].get("value") is False:
            fields["has_bond"].update(value=True, confidence=0.85, source="inferred")
    return fields
