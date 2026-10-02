"""Orchestrator Agent (supervisor) for the upload workflow, built as a LangGraph state graph.

    intake ─┬─(scanned)─▶ ocr ─┐
            └──────────────────┴▶ classify ─▶ privacy ─▶ extraction ─┬─(uncertain)─▶ confirm ─┐
                                                                      └────────────────────────┴▶ verification ─▶ finalize
    any step ──(not an offer letter / PII left / unreadable)──▶ reject
    any step ──(failed after 2 retries / over budget)─────────▶ escalate (human)

* Retries a failed step at most `max_retries` times, then escalates to a moderator.
* Enforces a token budget per run and a recursion limit against runaway loops.
* Pauses with `interrupt()` while the uploader confirms uncertain fields; the checkpoint lives
  in memory only (InMemorySaver), so document text is never written to disk.
* Logs every step to `agent_runs`.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from typing import Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agents import extraction, privacy, verification
from core import llm, runlog
from core.config import settings
from core.runlog import RunContext
from core.state import UploadState
from tools import database as db
from tools import documents

log = logging.getLogger("bondcheck.orchestrator")
O = "Orchestrator"


class NotOfferLetter(ValueError):
    pass


# Terminal, user-facing problems: no point retrying these.
REJECTIONS = (NotOfferLetter, privacy.PrivacyRejected, documents.UnsupportedDocument, documents.OCRUnavailable)

OFFER_WORDS = ["offer", "appointment", "employment", "ctc", "cost to company", "joining", "designation", "salary",
               "remuneration", "service agreement", "bond", "probation", "notice period", "position", "annexure",
               "compensation", "trainee", "date of joining", "terms and conditions", "hr"]
INJECTION = re.compile(r"(?i)(ignore (all |any )?(previous|prior|above) instructions|system prompt|you are (an? )?(ai|"
                       r"assistant|language model)|disregard (the )?(rules|instructions)|set (the )?\w+ to (0|zero|null))")


# --------------------------------------------------------------------------- nodes

def node_intake(state: UploadState, ctx: RunContext) -> dict:
    doc = documents.extract_text(state["document_bytes"], state.get("filename", ""))
    ctx.emit(O, "tool", f"extract_text: {doc.kind}, {doc.pages} page(s), {len(doc.text)} characters"
             + (" — looks scanned" if doc.is_scanned else ""))
    return {"raw_text": doc.text, "is_scanned": doc.is_scanned, "doc_kind": doc.kind}


def node_ocr(state: UploadState, ctx: RunContext) -> dict:
    ctx.emit(O, "decision", "Scanned document: routing to OCR before extraction")
    pages = documents.page_images(state["document_bytes"], state.get("doc_kind", "pdf"))
    texts = []
    for i, png in enumerate(pages, 1):
        texts.append(documents.ocr_image(png, ctx.meter))
        ctx.emit(O, "tool", f"ocr_image: page {i}/{len(pages)} transcribed")
    text = "\n\n".join(texts).strip()
    if len(text) < 80:
        raise documents.UnsupportedDocument("we couldn't read any text in this scan; try a clearer photo or the PDF")
    return {"raw_text": text}


def node_classify(state: UploadState, ctx: RunContext) -> dict:
    text = state["raw_text"]
    low = text.lower()
    hits = [w for w in OFFER_WORDS if w in low]
    if INJECTION.search(text):
        ctx.emit(O, "info", "Document contains instruction-like text; it is treated as data only and never followed")
    is_offer = len(hits) >= 4
    if not settings.offline:
        out = llm.json_call(
            model=settings.fast_model,
            system="You classify uploaded documents. " + llm.DATA_ONLY_RULE,
            prompt="Is this an employment offer letter, appointment letter, or service/bond agreement from an "
                   f"employer?\n\n<document>\n{text[:6000]}\n</document>",
            schema={"type": "object", "additionalProperties": False, "required": ["is_offer_letter", "reason"],
                    "properties": {"is_offer_letter": {"type": "boolean"}, "reason": {"type": "string"}}},
            meter=ctx.meter, max_tokens=400)
        is_offer = bool(out["is_offer_letter"])
        ctx.emit(O, "tool", f"classify_document (Haiku): {'offer letter' if is_offer else 'not an offer letter'} — "
                            f"{out['reason']}")
    else:
        ctx.emit(O, "tool", f"classify_document: {len(hits)} offer-letter signals ({', '.join(hits[:6])})")
    if not is_offer:
        raise NotOfferLetter("This doesn't look like an offer letter or service agreement, so we didn't process it. "
                             "Thanks for trying to help, though!")
    ctx.emit(O, "decision", "Plan: Privacy → Extraction (self-check) → [uploader confirmation] → Verification")
    return {"is_offer_letter": True}


def node_privacy(state: UploadState, ctx: RunContext) -> dict:
    redacted, report = privacy.run(state["raw_text"], ctx)
    # The original text and file leave the state here; only redacted text continues.
    return {"redacted_text": redacted, "privacy_passed": True, "privacy_report": report,
            "raw_text": "", "document_bytes": b""}


def node_extraction(state: UploadState, ctx: RunContext) -> dict:
    fields, needs, questions = extraction.run(state["redacted_text"], ctx, state.get("batch_year_hint"))
    return {"extracted": fields, "needs_user_confirmation": needs, "questions": questions}


def node_confirm(state: UploadState) -> dict:
    """Human-in-the-loop: pause until the uploader answers. (Not wrapped: interrupt must propagate.)"""
    answers = interrupt({"questions": state.get("questions", [])})
    ctx = runlog.get(state["upload_id"])
    fields = extraction.apply_answers(state["extracted"], state.get("questions", []), answers or {})
    ctx.emit(O, "info", f"Uploader answered {len(answers or {})} question(s); resuming", answers=answers)
    return {"extracted": fields, "answers": answers or {}, "needs_user_confirmation": []}


def node_verification(state: UploadState, ctx: RunContext) -> dict:
    fields = state["extracted"]
    if not fields.get("company_name", {}).get("value"):
        raise NotOfferLetter("We couldn't identify the company in this letter, so it can't be added.")
    res = verification.run(fields, ctx)
    return {"verification_decision": res["decision"], "record_id": res["record_id"],
            "company_id": res["company_id"], "decision_detail": res}


MESSAGES = {
    "corroborate": "Thank you! Your letter matched earlier uploads and made this company's data more reliable.",
    "variant": "Thank you! Your letter was added as a new batch/role variant for this company.",
    "conflict": "Thank you! Your letter reports different terms from earlier uploads. Both are shown openly and a "
                "moderator will review the difference.",
    "outlier": "Thank you! Some values look unusual, so a moderator will check them before they are published.",
    "new_company": "Thank you! This company is new to BondCheck. A moderator will review it before it's published.",
}


def node_finalize(state: UploadState) -> dict:
    ctx = runlog.get(state["upload_id"])
    decision = state.get("verification_decision")
    status = "stored" if decision in {"corroborate", "variant", "conflict"} else "queued"
    ctx.emit(O, "done", "Run complete. The uploaded document and its text were deleted from memory.",
             decision=decision, record_id=state.get("record_id"))
    ctx.log_orchestrator("success")
    return {"status": status, "message": MESSAGES.get(decision, "Done."), "raw_text": "", "redacted_text": "",
            "document_bytes": b""}


def node_reject(state: UploadState) -> dict:
    ctx = runlog.get(state["upload_id"])
    ctx.emit(O, "decision", f"Rejected: {state.get('message')}")
    ctx.log_orchestrator("failed")
    return {"raw_text": "", "redacted_text": "", "document_bytes": b""}


def node_escalate(state: UploadState) -> dict:
    ctx = runlog.get(state["upload_id"])
    note = "; ".join(state.get("errors", [])[-3:]) or state.get("message", "")
    db.insert("moderation_queue", {"record_id": None, "reason": "escalated", "note": f"run {ctx.run_ref}: {note}"[:900]})
    ctx.emit(O, "decision", "Escalated to a human moderator after repeated failures")
    ctx.log_orchestrator("escalated")
    return {"message": "Something went wrong while reading your letter. A moderator has been notified; "
                       "nothing from your document was stored.",
            "raw_text": "", "redacted_text": "", "document_bytes": b""}


# --------------------------------------------------------------------------- guarded execution

def guarded(name: str, fn: Callable[[UploadState, RunContext], dict]):
    """Retry up to max_retries, enforce the token budget, convert failures into routing decisions."""
    def node(state: UploadState) -> dict:
        ctx = runlog.get(state["upload_id"])
        retries = dict(state.get("retries") or {})
        errors = list(state.get("errors") or [])
        while True:
            try:
                ctx.meter.check()
                update = fn(state, ctx)
                ctx.meter.check()
                return {**update, "retries": retries, "errors": errors, "cost_tokens": ctx.meter.used}
            except REJECTIONS as e:
                return {"status": "rejected", "message": str(e), "errors": errors + [f"{name}: {e}"],
                        "retries": retries, "cost_tokens": ctx.meter.used}
            except llm.BudgetExceeded as e:
                ctx.emit(O, "decision", f"Stopping: {e}")
                return {"status": "escalated", "errors": errors + [f"{name}: {e}"], "retries": retries,
                        "cost_tokens": ctx.meter.used}
            except Exception as e:  # noqa: BLE001 - every other failure is retried, then escalated
                log.exception("%s failed", name)
                retries[name] = retries.get(name, 0) + 1
                errors.append(f"{name}: {type(e).__name__}: {e}")
                if retries[name] > settings.max_retries:
                    ctx.emit(O, "decision", f"{name} failed {retries[name]} times; escalating to a human")
                    return {"status": "escalated", "errors": errors, "retries": retries,
                            "cost_tokens": ctx.meter.used}
                ctx.emit(O, "retry", f"{name} failed ({type(e).__name__}); retry {retries[name]}/{settings.max_retries}")
    node.__name__ = f"node_{name}"
    return node


def _route(next_ok: str):
    def r(state: UploadState) -> str:
        st = state.get("status")
        if st == "rejected":
            return "reject"
        if st == "escalated":
            return "escalate"
        return next_ok
    return r


def _route_intake(state: UploadState) -> str:
    base = _route("classify")(state)
    if base != "classify":
        return base
    return "ocr" if state.get("is_scanned") else "classify"


def _route_extraction(state: UploadState) -> str:
    base = _route("verification")(state)
    if base != "verification":
        return base
    return "confirm" if state.get("needs_user_confirmation") else "verification"


def build_graph(checkpointer=None):
    g = StateGraph(UploadState)
    g.add_node("intake", guarded("intake", node_intake))
    g.add_node("ocr", guarded("ocr", node_ocr))
    g.add_node("classify", guarded("classify", node_classify))
    g.add_node("privacy", guarded("privacy", node_privacy))
    g.add_node("extraction", guarded("extraction", node_extraction))
    g.add_node("confirm", node_confirm)
    g.add_node("verification", guarded("verification", node_verification))
    g.add_node("finalize", node_finalize)
    g.add_node("reject", node_reject)
    g.add_node("escalate", node_escalate)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", _route_intake, ["ocr", "classify", "reject", "escalate"])
    g.add_conditional_edges("ocr", _route("classify"), ["classify", "reject", "escalate"])
    g.add_conditional_edges("classify", _route("privacy"), ["privacy", "reject", "escalate"])
    g.add_conditional_edges("privacy", _route("extraction"), ["extraction", "reject", "escalate"])
    g.add_conditional_edges("extraction", _route_extraction, ["confirm", "verification", "reject", "escalate"])
    g.add_edge("confirm", "verification")
    g.add_conditional_edges("verification", _route("finalize"), ["finalize", "reject", "escalate"])
    g.add_edge("finalize", END)
    g.add_edge("reject", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


_checkpointer = InMemorySaver()
GRAPH = build_graph(_checkpointer)


# --------------------------------------------------------------------------- public API

def _config(upload_id: str) -> dict:
    return {"configurable": {"thread_id": upload_id}, "recursion_limit": 30}


def _public_fields(fields: dict | None) -> dict:
    if not fields:
        return {}
    return {f: {"value": v.get("value"), "quote": v.get("quote"), "confidence": v.get("confidence"),
                "source": v.get("source"), "checks": v.get("checks", [])} for f, v in fields.items()}


def _result(upload_id: str) -> dict:
    snap = GRAPH.get_state(_config(upload_id))
    s = snap.values
    if snap.next and "confirm" in snap.next:
        return {"upload_id": upload_id, "status": "needs_confirmation", "questions": s.get("questions", []),
                "extracted": _public_fields(s.get("extracted")), "privacy_report": s.get("privacy_report"),
                "message": "Please confirm a few details we weren't sure about.", "tokens": s.get("cost_tokens", 0)}
    status = s.get("status")
    if status not in {"rejected", "escalated", "stored", "queued"}:
        status = "escalated"
    return {"upload_id": upload_id, "status": status, "message": s.get("message"),
            "decision": s.get("verification_decision"), "decision_detail": s.get("decision_detail"),
            "record_id": s.get("record_id"), "company_id": s.get("company_id"),
            "extracted": _public_fields(s.get("extracted")), "privacy_report": s.get("privacy_report"),
            "tokens": s.get("cost_tokens", 0)}


def _run_in_thread(ctx: RunContext, payload, upload_id: str) -> None:
    def target():
        try:
            GRAPH.invoke(payload, _config(upload_id))
            ctx.result = _result(upload_id)
            if ctx.result["status"] == "needs_confirmation":
                ctx.emit(O, "ask", "Paused: waiting for the uploader to confirm uncertain fields")
                ctx.log_orchestrator("paused")
            else:
                _forget(upload_id)
        except Exception as e:  # noqa: BLE001
            log.exception("upload run crashed")
            ctx.result = {"upload_id": upload_id, "status": "escalated", "message": f"Unexpected error: {e}"}
            ctx.log_orchestrator("failed")
            _forget(upload_id)
        finally:
            ctx.events.put({"kind": "result", "result": ctx.result})
            ctx.events.put(None)

    threading.Thread(target=target, daemon=True).start()


def _forget(upload_id: str) -> None:
    """Delete the in-memory checkpoint: the document is gone for good."""
    try:
        _checkpointer.delete_thread(upload_id)
    except Exception:  # noqa: BLE001
        pass


def start_upload(data: bytes, filename: str, batch_year_hint: int | None = None, background: bool = True) -> RunContext:
    upload_id = uuid.uuid4().hex[:12]
    ctx = runlog.register(RunContext("upload", run_ref=upload_id))
    ctx.emit(O, "start", f"New upload received: {filename or 'document'} ({len(data) // 1024 + 1} KB)")
    state: UploadState = {"upload_id": upload_id, "document_bytes": data, "filename": filename,
                          "batch_year_hint": batch_year_hint, "errors": [], "retries": {}, "cost_tokens": 0,
                          "status": "running"}
    if background:
        _run_in_thread(ctx, state, upload_id)
    else:
        GRAPH.invoke(state, _config(upload_id))
        ctx.result = _result(upload_id)
        if ctx.result["status"] != "needs_confirmation":
            _forget(upload_id)
    return ctx


def resume_upload(upload_id: str, answers: dict, background: bool = True) -> RunContext:
    snap = GRAPH.get_state(_config(upload_id))
    if not snap.next or "confirm" not in snap.next:
        raise KeyError("this upload is not waiting for confirmation (it may have expired)")
    old = runlog._CONTEXTS.get(upload_id)
    ctx = RunContext("upload", run_ref=upload_id)
    if old:
        ctx.meter = old.meter
    runlog.register(ctx)
    ctx.emit(O, "start", "Resuming with the uploader's answers")
    if background:
        _run_in_thread(ctx, Command(resume=answers), upload_id)
    else:
        GRAPH.invoke(Command(resume=answers), _config(upload_id))
        ctx.result = _result(upload_id)
        _forget(upload_id)
    return ctx
