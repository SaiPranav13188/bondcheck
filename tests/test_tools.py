import pytest

from tools import pii
from tools.calculator import calc_exit_cost, inr
from tools.documents import read_section, verify_quote
from tools.normalize import normalize_amount, normalize_days, normalize_duration, words_to_number


@pytest.mark.parametrize("text,expected", [
    ("Rs. 1,50,000/-", [150000]),
    ("Rupees One Lakh Fifty Thousand only", [150000]),
    ("4.5 LPA", [450000]),
    ("₹1.5 lakh", [150000]),
    ("INR 2,00,000", [200000]),
    ("Rs. 35,000 per month", [420000]),
])
def test_normalize_amount(text, expected):
    assert normalize_amount(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("24 (twenty-four) months", 24), ("two (2) years", 24), ("18 months", 18), ("one year", 12), ("1.5 years", 18),
])
def test_normalize_duration(text, expected):
    assert normalize_duration(text) == expected


def test_normalize_days_and_words():
    assert normalize_days("giving 90 days' notice") == 90
    assert words_to_number("Two Lakh Fifty Thousand") == 250000


def test_calc_exit_cost_is_deterministic():
    full = calc_exit_cost(150000, 24, 10, "not_mentioned")
    assert full["amount"] == 150000
    pro = calc_exit_cost(120000, 24, 6, "yes")
    assert pro["amount"] == 90000
    assert calc_exit_cost(100000, 12, 12, "no")["amount"] == 0
    assert calc_exit_cost(None, 12, 3, "no")["amount"] is None


def test_inr_grouping():
    assert inr(150000) == "₹1,50,000"
    assert inr(12500000) == "₹1,25,00,000"
    assert inr(999) == "₹999"


def test_verify_quote_catches_made_up_quotes():
    doc = "You shall serve the Company for a minimum period of 24 months.\nNotice period: 90 days."
    assert verify_quote("serve the company for a minimum   period of 24 months", doc)["found"]
    assert not verify_quote("you must pay Rs. 5,00,000 if you leave", doc)["found"]


def test_read_section_returns_relevant_clause():
    doc = "1. Probation is 6 months.\n\n2. You will serve a bond of 24 months.\n\n3. Notice period is 60 days."
    assert read_section(doc, "bond").startswith("2. You will serve a bond")


def test_privacy_redacts_and_rescan_is_clean():
    text = ("To,\nMs. Diya Sharma\nH.No. 12-4, MG Road\nPune, Maharashtra - 411004\n"
            "Candidate ID: NX12345\nContact: +91 9876543210 | diya.sharma@gmail.com\nPAN: ABCDE1234F\n"
            "Aadhaar No.: 2345 6789 0123\n\nDear Diya,\nWe offer you the role.\n\nAccepted by: Diya Sharma")
    red = pii.redact(text, pii.detect_pii(text, use_llm=False))
    for secret in ["Diya", "Sharma", "MG Road", "411004", "NX12345", "9876543210", "gmail", "ABCDE1234F", "2345 6789"]:
        assert secret not in red, secret
    assert pii.scan_for_remaining_pii(red, use_llm=False) == []


def test_rescan_finds_what_detect_missed():
    text = "[REDACTED_NAME]\nFlat 3, Lotus Apartments\nCandidate ref EMP77881 [REDACTED_PHONE]"
    found = {f["type"] for f in pii.scan_for_remaining_pii(text, use_llm=False)}
    assert "EMPLOYEE_ID" in found
