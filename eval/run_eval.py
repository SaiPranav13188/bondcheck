"""Evaluation: single-pass extraction vs the agentic loop, plus privacy, conflicts and Q&A.

    python -m eval.run_eval --generate   # (re)create the 50 synthetic letters + ground_truth.json
    python -m eval.run_eval              # run every metric, write eval/results.json and eval/report.md

The engine under test is whatever is configured: Claude when ANTHROPIC_API_KEY is set,
otherwise the offline rule engine. Results always record which engine produced them.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

from agents import extraction, privacy
from core.config import ROOT, settings
from core.runlog import RunContext
from eval.letters import COMPANIES, make_letter, render_pdf
from tools import documents

EVAL_DIR = ROOT / "eval"
LETTER_DIR = EVAL_DIR / "synthetic_letters"
TRUTH_PATH = EVAL_DIR / "ground_truth.json"
N_LETTERS = 50
SCANNED = {7, 19, 28, 36, 44}  # indexes rendered as image-only scans
FIELDS = list(extraction.FIELDS)


# ---------------------------------------------------------------- data

def generate() -> None:
    rng = random.Random(50)
    LETTER_DIR.mkdir(parents=True, exist_ok=True)
    templates = ["formal", "tricky", "table", "annexure", "email"]
    truth = {}
    for i in range(N_LETTERS):
        L = make_letter(i, rng, template=templates[i % len(templates)])
        scanned = i in SCANNED
        (LETTER_DIR / f"{L.id}.pdf").write_bytes(render_pdf(L.text, scanned=scanned, seed=i))
        truth[L.id] = {"file": f"{L.id}.pdf", "fields": L.truth, "pii": L.pii, "template": L.template,
                       "tags": L.tags + (["scanned"] if scanned else []), "scanned": scanned}
    TRUTH_PATH.write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {N_LETTERS} letters to {LETTER_DIR} and {TRUTH_PATH.name}")


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def field_correct(field: str, got, want) -> bool:
    if field == "other_risky_clauses":
        return sorted(got or []) == sorted(want or [])
    if want is None or got is None:
        return want is None and got is None
    if field in {"company_name", "role"}:
        return _norm(got) == _norm(want) or fuzz.token_sort_ratio(str(got).lower(), str(want).lower()) >= 90
    return got == want


def hallucinated(field: str, fv: dict, text: str, want) -> bool:
    """A stored value with no real support: its quote isn't in the document, or the field doesn't exist."""
    v = fv.get("value")
    if v in (None, [], False, "not_mentioned") or fv.get("source") in {"default", "uploader_hint"}:
        return False
    if want in (None, [], False, "not_mentioned"):
        return True
    quote = fv.get("quote") or ""
    return not documents.verify_quote(quote, text)["found"]


# ---------------------------------------------------------------- extraction + privacy

def eval_extraction(truth: dict) -> dict:
    per_mode = {"single_pass": Counter(), "agentic": Counter(), "agentic_confirmed": Counter()}
    halluc = {"single_pass": 0, "agentic": 0}
    errors_by_field = {"single_pass": Counter(), "agentic": Counter()}
    pii_total = pii_leaks_text = pii_leaks_stored = 0
    privacy_attempts = Counter()
    questions = 0
    letters_with_questions = 0
    times, tokens = [], []
    processed = skipped_scanned = 0
    per_letter = []

    for lid, t in truth.items():
        data = (LETTER_DIR / t["file"]).read_bytes()
        doc = documents.extract_text(data, t["file"])
        start = time.perf_counter()
        ctx = RunContext("eval", persist=False)
        text = doc.text
        if doc.is_scanned:
            try:
                text = "\n\n".join(documents.ocr_image(p, ctx.meter) for p in documents.page_images(data, doc.kind))
            except documents.OCRUnavailable:
                skipped_scanned += 1
                per_letter.append({"id": lid, "skipped": "scanned letter needs OCR (Tesseract or Claude vision)"})
                continue
        processed += 1
        redacted, report = privacy.run(text, ctx)
        privacy_attempts[report["attempts"]] += 1
        pii = t["pii"]
        pii_total += len(pii)
        leaked_text = [p for p in pii if p in redacted]
        pii_leaks_text += len(leaked_text)

        engine = extraction.make_engine(ctx.meter)
        sp = extraction.single_pass(redacted, engine)
        ag, needs, qs = extraction.run(redacted, ctx, engine=engine)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        tokens.append(ctx.meter.used)
        questions += len(qs)
        letters_with_questions += bool(qs)

        stored_quotes = " ".join((fv.get("quote") or "") + " ".join(fv.get("quotes") or []) for fv in ag.values())
        leaked_stored = [p for p in pii if p in stored_quotes]
        pii_leaks_stored += len(leaked_stored)

        from db.seed import answer_from_truth  # simulated uploader

        confirmed = extraction.apply_answers({f: dict(v) for f, v in ag.items()}, qs, answer_from_truth(qs, t["fields"]))
        wrong = {"single_pass": [], "agentic": []}
        for f in FIELDS:
            want = t["fields"][f]
            for mode, res in (("single_pass", sp), ("agentic", ag), ("agentic_confirmed", confirmed)):
                ok = field_correct(f, res[f].get("value"), want)
                per_mode[mode]["correct" if ok else "wrong"] += 1
                if not ok and mode in wrong:
                    wrong[mode].append(f)
                    errors_by_field[mode][f] += 1
            halluc["single_pass"] += hallucinated(f, sp[f], redacted, want)
            halluc["agentic"] += hallucinated(f, ag[f], redacted, want)
        per_letter.append({"id": lid, "template": t["template"], "tags": t["tags"], "wrong_single_pass": wrong["single_pass"],
                           "wrong_agentic": wrong["agentic"], "questions": [q["field"] for q in qs],
                           "privacy_attempts": report["attempts"], "pii_leaked_in_redacted_text": leaked_text,
                           "seconds": round(elapsed, 3), "tokens": ctx.meter.used})

    def acc(c):
        n = c["correct"] + c["wrong"]
        return round(c["correct"] / n, 4) if n else None

    n_fields = processed * len(FIELDS)
    return {
        "letters": len(truth), "processed": processed, "skipped_scanned": skipped_scanned,
        "accuracy": {m: acc(c) for m, c in per_mode.items()},
        "hallucinated_fields": {m: v for m, v in halluc.items()},
        "hallucination_rate": {m: round(v / n_fields, 4) if n_fields else None for m, v in halluc.items()},
        "errors_by_field": {m: dict(c.most_common()) for m, c in errors_by_field.items()},
        "uploader_questions": {"total": questions, "letters_with_questions": letters_with_questions},
        "privacy": {"pii_items": pii_total, "leaked_in_redacted_text": pii_leaks_text,
                    "leaked_in_stored_records": pii_leaks_stored,
                    "stored_leak_rate": round(pii_leaks_stored / pii_total, 4) if pii_total else None,
                    "redacted_text_leak_rate": round(pii_leaks_text / pii_total, 4) if pii_total else None,
                    "rescan_attempts": dict(sorted(privacy_attempts.items()))},
        "cost": {"avg_seconds_per_letter": round(sum(times) / len(times), 3) if times else None,
                 "avg_tokens_per_letter": round(sum(tokens) / len(tokens)) if tokens else 0},
        "per_letter": per_letter,
    }


# ---------------------------------------------------------------- conflicts + Q&A (isolated database)

def eval_conflicts_and_qa() -> dict:
    """Upload batches of letters where some companies have injected disagreements, then measure
    conflict precision/recall and whether Q&A answers cite the right records."""
    from agents import orchestrator, qa
    from db.seed import approve_pending, run_letter
    from tools import database as db

    tmp = Path(tempfile.mkdtemp()) / "eval.db"
    object.__setattr__(settings, "sqlite_path", tmp)
    db.init_db(reset=True)
    rng = random.Random(7)
    expected_conflicts = set()
    plan = []
    for i, co in enumerate(COMPANIES[:12]):
        overrides = []
        if i % 3 == 0 and co["bond"]:  # inject a disagreement for every third bonded company
            overrides = [{"penalty": co["penalty"] // 2}]
            expected_conflicts.add((co["name"], 2026, "penalty_amount"))
        plan.append((co, [{}] * 3 + overrides))
    idx = 1000
    for co, variants in plan:
        for k, ov in enumerate(variants):
            idx += 1
            res = run_letter(make_letter(idx, rng, co, 2026, overrides=ov))
            if res.get("decision") == "new_company" and k == 0:
                approve_pending(res["record_id"])
    found = {(r["name"], r["batch_year"], r["field"]) for r in
             db.query("SELECT c.name, f.batch_year, f.field FROM conflicts f JOIN companies c ON c.id = f.company_id")}
    tp = len(found & expected_conflicts)
    precision = tp / len(found) if found else 1.0
    recall = tp / len(expected_conflicts) if expected_conflicts else 1.0

    # Q&A: does every answer cite only records that really belong to the company it talks about?
    qa_total = qa_ok = 0
    qa_rows = []
    for co, _ in plan:
        for q in (f"What is the bond at {co['short']}?",
                  f"If I join {co['short']} and leave after 6 months, what could I owe?"):
            ctx = RunContext("eval-qa", persist=False)
            out = qa.answer(q, ctx)
            cid = db.find_company(co["name"])[0]["id"]
            valid = {r["id"] for r in db.query("SELECT id FROM offer_records WHERE company_id = ? AND status = 'verified'",
                                               [cid])}
            cited = {c["record_id"] for c in out["citations"]}
            ok = bool(cited) and cited <= valid and "not legal advice" in out["answer"].lower()
            qa_total += 1
            qa_ok += ok
            qa_rows.append({"question": q, "cited": sorted(cited), "ok": ok})
    return {
        "conflicts": {"expected": len(expected_conflicts), "found": len(found), "true_positives": tp,
                      "precision": round(precision, 4), "recall": round(recall, 4)},
        "qa": {"questions": qa_total, "correct_citations": qa_ok,
               "citation_accuracy": round(qa_ok / qa_total, 4) if qa_total else None, "rows": qa_rows},
    }


# ---------------------------------------------------------------- report

def write_report(res: dict) -> None:
    x, c = res["extraction"], res["conflicts_qa"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = [
        "# BondCheck evaluation report", "",
        f"*Generated {res['generated_at']} · engine: **{res['engine']}** · "
        f"{x['letters']} synthetic letters ({x['processed']} processed, {x['skipped_scanned']} scanned skipped: no OCR)*", "",
        "## Single-pass extraction vs the agentic loop", "",
        "| | Single-pass extraction | Agentic (self-check + re-read) | Agentic + uploader confirmation |",
        "|---|---|---|---|",
        f"| Field accuracy | {pct(x['accuracy']['single_pass'])} | {pct(x['accuracy']['agentic'])} | "
        f"{pct(x['accuracy']['agentic_confirmed'])} |",
        f"| Hallucinated fields | {x['hallucinated_fields']['single_pass']} | {x['hallucinated_fields']['agentic']} | — |",
        f"| Avg time per letter | — | {x['cost']['avg_seconds_per_letter']} s | — |",
        f"| Avg tokens per letter | — | {x['cost']['avg_tokens_per_letter']} | — |", "",
        f"Uploader questions: {x['uploader_questions']['total']} across "
        f"{x['uploader_questions']['letters_with_questions']} letters.", "",
        "## Targets", "",
        "| Metric | Target | Result |", "|---|---|---|",
        f"| Field-level extraction accuracy | ≥ 90% | {pct(x['accuracy']['agentic'])} |",
        f"| PII leak rate (personal data in stored records) | 0% | {pct(x['privacy']['stored_leak_rate'])} |",
        f"| Hallucinated values stored | 0% | {pct(x['hallucination_rate']['agentic'])} |",
        f"| Conflict detection precision / recall | ≥ 85% | {pct(c['conflicts']['precision'])} / {pct(c['conflicts']['recall'])} |",
        f"| Q&A answers with correct citations | ≥ 95% | {pct(c['qa']['citation_accuracy'])} |",
        f"| Average cost and time per upload | measured | {x['cost']['avg_tokens_per_letter']} tokens, "
        f"{x['cost']['avg_seconds_per_letter']} s |", "",
        "## Privacy", "",
        f"- PII items planted: {x['privacy']['pii_items']}",
        f"- Leaked into stored evidence: {x['privacy']['leaked_in_stored_records']}",
        f"- Still present anywhere in the redacted text: {x['privacy']['leaked_in_redacted_text']} "
        f"({pct(x['privacy']['redacted_text_leak_rate'])})",
        f"- Re-scan attempts needed: {x['privacy']['rescan_attempts']}", "",
        "## Where errors remain", "",
        f"- Single-pass: {x['errors_by_field']['single_pass']}",
        f"- Agentic: {x['errors_by_field']['agentic']}", "",
    ]
    lines += ["> **Caveat:** the test letters come from the same generator the extraction rules were developed "
              "against (different random seeds). Treat these as an upper bound and add real, consented letters to the "
              "test set before quoting the numbers.", ""]
    if res["engine"] == "offline rule engine":
        lines += ["> These numbers come from the offline rule engine. Set `ANTHROPIC_API_KEY` and re-run "
                  "`python -m eval.run_eval` to measure the Claude-based extraction (and OCR for the scanned letters).", ""]
    (EVAL_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="regenerate the synthetic letters first")
    args = ap.parse_args()
    if args.generate or not TRUTH_PATH.exists():
        generate()
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    res = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "engine": "offline rule engine" if settings.offline else f"Claude ({settings.strong_model} / {settings.fast_model})",
        "extraction": eval_extraction(truth),
    }
    res["conflicts_qa"] = eval_conflicts_and_qa()
    (EVAL_DIR / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(res)
    x = res["extraction"]
    print(json.dumps({"accuracy": x["accuracy"], "hallucinated": x["hallucinated_fields"], "privacy": x["privacy"],
                      "conflicts": res["conflicts_qa"]["conflicts"], "qa": res["conflicts_qa"]["qa"]["citation_accuracy"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
