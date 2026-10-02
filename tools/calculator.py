"""calc_exit_cost: plain Python, never the LLM, so the arithmetic is always right."""
from __future__ import annotations


def inr(n: float | int | None) -> str:
    """Indian digit grouping: 150000 -> '₹1,50,000'."""
    if n is None:
        return "unknown"
    n = int(round(n))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}"


def calc_exit_cost(penalty: int | None, bond_months: int | None, months_served: float,
                   prorated: str = "not_mentioned") -> dict:
    """What a student might owe if they leave after `months_served` months.

    prorated: 'yes' -> penalty reduced in proportion to time served;
              'no' / 'not_mentioned' -> the full penalty may apply.
    """
    if penalty is None or bond_months is None:
        return {"amount": None, "explanation": "The bond amount or duration is not known, so the cost cannot be computed.",
                "formula": None}
    if bond_months <= 0 or penalty <= 0:
        return {"amount": 0, "explanation": "No bond penalty applies.", "formula": None}
    served = max(0.0, float(months_served))
    remaining = max(0.0, bond_months - served)
    if remaining == 0:
        return {"amount": 0, "remaining_months": 0,
                "explanation": f"You would have completed the full {bond_months}-month bond, so no penalty applies.",
                "formula": f"{served:g} ≥ {bond_months} months served"}
    if prorated == "yes":
        amount = penalty * remaining / bond_months
        return {"amount": int(round(amount)), "remaining_months": remaining,
                "explanation": f"The penalty is pro-rated: {inr(penalty)} × {remaining:g}/{bond_months} months remaining "
                               f"= {inr(amount)}.",
                "formula": f"{penalty} × ({bond_months} − {served:g}) / {bond_months}"}
    note = ("The letters say the full amount applies regardless of time served."
            if prorated == "no" else
            "The letters do not mention reducing the penalty for time served, so the full amount may apply. "
            "Ask HR whether it is pro-rated.")
    return {"amount": int(penalty), "remaining_months": remaining,
            "explanation": f"Full penalty of {inr(penalty)}. {note}", "formula": f"{penalty} (not pro-rated)"}
