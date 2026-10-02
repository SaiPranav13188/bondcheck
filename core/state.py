"""Shared state passed between the upload-workflow agents (LangGraph state)."""
from __future__ import annotations

from typing import TypedDict


class FieldValue(TypedDict, total=False):
    value: object
    quote: str
    confidence: float
    source: str          # extracted | reread | uploader_confirmed | uploader_corrected | default
    checks: list[str]


class UploadState(TypedDict, total=False):
    upload_id: str
    raw_text: str                 # in memory only, never stored
    is_scanned: bool
    redacted_text: str
    privacy_passed: bool
    extracted: dict               # field -> {value, quote, confidence}
    needs_user_confirmation: list[str]
    verification_decision: str    # corroborate | variant | conflict | outlier | new_company
    record_id: int | None
    errors: list[str]
    retries: dict[str, int]
    cost_tokens: int

    # --- additions needed to run the graph ---
    filename: str
    document_bytes: bytes         # in memory only; cleared after the Privacy Agent
    doc_kind: str                 # pdf | image | text
    is_offer_letter: bool
    batch_year_hint: int | None   # the uploader may tell us their batch
    privacy_report: dict
    questions: list[dict]         # questions put to the uploader
    answers: dict                 # uploader's answers
    company_id: int | None
    decision_detail: dict
    status: str                   # running | needs_confirmation | stored | queued | rejected | escalated
    message: str                  # user-facing outcome
