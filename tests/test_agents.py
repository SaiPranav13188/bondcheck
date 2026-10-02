import random

import pytest

from agents import extraction, orchestrator, qa, verification
from core.runlog import RunContext
from eval.letters import COMPANIES, make_letter, render_pdf
from tools import database as db


def _ctx():
    return RunContext("test", persist=False)


def test_extraction_self_corrects_probation_trap():
    letter = make_letter(1, random.Random(3), COMPANIES[0], 2026, "tricky")
    single = extraction.single_pass(letter.text, extraction.RuleEngine())
    fields, needs, _ = extraction.run(letter.text, _ctx())
    assert fields["bond_months"]["value"] == 24
    assert fields["penalty_amount"]["value"] == 150000
    # the first pass is fooled by the probation clause; the agentic loop is not
    assert single["bond_months"]["value"] != 24
    assert not needs


def test_extraction_drops_unverifiable_values():
    fv = {"value": 999999, "quote": "a penalty of Rs. 9,99,999 applies", "confidence": 0.9, "source": "extracted"}
    problems = extraction.check_field("penalty_amount", fv, "This letter has no such clause.")
    assert problems and problems[0].startswith("quote_not_found")


def test_negated_bond_is_caught():
    fv = {"value": True, "quote": "There is no bond or service agreement associated with this offer.",
          "confidence": 0.9, "source": "extracted"}
    doc = "There is no bond or service agreement associated with this offer."
    assert any(p.startswith("negated") for p in extraction.check_field("has_bond", fv, doc))


def test_outlier_rules():
    assert verification.outlier_reasons({"penalty_amount": 5_000_000, "ctc_annual": 400000})
    assert not verification.outlier_reasons({"penalty_amount": 150000, "bond_months": 24, "ctc_annual": 400000})


def test_compare_records():
    existing = [{"has_bond": True, "bond_months": 24, "penalty_amount": 150000}] * 3
    assert verification.compare_records({"has_bond": True, "bond_months": 24, "penalty_amount": 150000}, existing)["matches"]
    diff = verification.compare_records({"has_bond": True, "bond_months": 24, "penalty_amount": 75000}, existing)
    assert diff["differing"] == {"penalty_amount": {"150000": 3, "75000": 1}}


def test_readonly_sql_guardrails(seeded_db):
    assert db.run_readonly_sql("SELECT COUNT(*) AS n FROM offer_records")[0]["n"] > 0
    for bad in ["DELETE FROM offer_records", "SELECT * FROM users", "SELECT 1; DROP TABLE companies",
                "UPDATE offer_records SET status='verified'", "SELECT * FROM agent_runs"]:
        with pytest.raises(db.UnsafeQuery):
            db.run_readonly_sql(bad)
    assert len(db.run_readonly_sql("SELECT * FROM evidence")) <= 200  # automatic LIMIT


def test_find_company_fuzzy(seeded_db):
    assert db.find_company("Nexora Tech Pvt Ltd")[0]["name"].startswith("Nexora")
    assert db.find_company("quantiva systems")[0]["score"] >= 90


def test_full_upload_workflow_corroborates(seeded_db):
    letter = make_letter(500, random.Random(11), COMPANIES[0], 2026, "formal")
    ctx = orchestrator.start_upload(render_pdf(letter.text), "x.pdf", background=False)
    assert ctx.result["status"] == "stored"
    assert ctx.result["decision"] == "corroborate"
    stored = db.get_evidence(ctx.result["record_id"])
    blob = " ".join(e["quote"] for e in stored["evidence"])
    for secret in letter.pii:
        assert secret not in blob


def test_upload_pauses_for_uploader_and_resumes(seeded_db):
    text = make_letter(501, random.Random(12), COMPANIES[13], 2026, "formal").text
    text = "\n".join(
        "4. You agree to serve the Company for a minimum period of 12 months, failing which liquidated damages "
        "as determined by the management are payable." if ("bond amount" in ln or "liquidated" in ln or "sum of" in ln)
        else ln for ln in text.split("\n"))
    ctx = orchestrator.start_upload(render_pdf(text), "y.pdf", background=False)
    assert ctx.result["status"] == "needs_confirmation"
    assert "penalty_amount" in [q["field"] for q in ctx.result["questions"]]
    ctx2 = orchestrator.resume_upload(ctx.result["upload_id"], {"penalty_amount": "50000"}, background=False)
    assert ctx2.result["status"] == "stored"
    assert db.get_evidence(ctx2.result["record_id"])["penalty_amount"] == 50000


def test_non_offer_is_rejected(seeded_db):
    ctx = orchestrator.start_upload(b"Grocery list: milk, eggs, bread", "list.txt", background=False)
    assert ctx.result["status"] == "rejected"


def test_conflicting_upload_creates_conflict(seeded_db):
    co = next(c for c in COMPANIES if c["short"] == "Quantiva Systems")
    letter = make_letter(502, random.Random(13), co, 2026, "formal", overrides={"penalty": 40000})
    ctx = orchestrator.start_upload(render_pdf(letter.text), "z.pdf", background=False)
    assert ctx.result.get("decision") == "conflict", ctx.result
    assert db.query("SELECT * FROM conflicts WHERE company_id = ? AND status = 'open'", [ctx.result["company_id"]])


def test_qa_cites_records_and_uses_calculator(seeded_db):
    out = qa.answer("If I join Nexora and leave after 10 months, what could I owe?", _ctx())
    assert out["citations"]
    assert "₹1,50,000" in out["answer"]
    assert "not legal advice" in out["answer"].lower()
    nexora = db.find_company("Nexora")[0]["id"]
    valid = {r["id"] for r in db.query("SELECT id FROM offer_records WHERE company_id = ?", [nexora])}
    assert {c["record_id"] for c in out["citations"]} <= valid


def test_qa_admits_missing_data(seeded_db):
    out = qa.answer("What is the bond at Stellarbyte Technologies?", _ctx())
    assert "don't have any verified uploads" in out["answer"]
