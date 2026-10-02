"""Privacy Agent. Goal: guarantee that no personal information is ever stored.

Loop: detect -> redact -> independent re-scan -> redact again ... After 3 failed
attempts the upload is rejected rather than risk a leak.
"""
from __future__ import annotations

from collections import Counter

from core.config import settings
from core.runlog import RunContext
from tools import pii


class PrivacyRejected(RuntimeError):
    pass


def run(text: str, ctx: RunContext, use_llm: bool = True) -> tuple[str, dict]:
    use_llm = use_llm and not settings.offline
    with ctx.agent("Privacy Agent") as run_:
        spans = pii.detect_pii(text, meter=ctx.meter, use_llm=use_llm)
        kinds = Counter(s["type"] for s in spans)
        ctx.emit("Privacy Agent", "tool", f"detect_pii found {len(spans)} personal details",
                 types=dict(kinds))
        redacted = pii.redact(text, spans)
        ctx.emit("Privacy Agent", "tool", "redact applied")
        history = [{"attempt": 1, "detected": len(spans), "types": dict(kinds)}]

        for attempt in range(1, settings.privacy_max_attempts + 1):
            remaining = pii.scan_for_remaining_pii(redacted, meter=ctx.meter, use_llm=use_llm)
            history[-1]["remaining_after_rescan"] = len(remaining)
            if not remaining:
                ctx.emit("Privacy Agent", "check", f"Re-scan {attempt}: no personal data left", passed=True)
                report = {"passed": True, "attempts": attempt, "redactions": redacted.count("[REDACTED_"),
                          "history": history}
                return redacted, report
            ctx.emit("Privacy Agent", "retry",
                     f"Re-scan {attempt}: {len(remaining)} item(s) still visible "
                     f"({', '.join(sorted({r['type'] for r in remaining}))}); redacting again",
                     types=sorted({r["type"] for r in remaining}))
            if attempt == settings.privacy_max_attempts:
                break
            redacted = pii.redact(redacted, remaining)
            history.append({"attempt": attempt + 1, "detected": len(remaining),
                            "types": dict(Counter(r["type"] for r in remaining))})

        run_.status = "escalated"
        ctx.emit("Privacy Agent", "decision", "Personal data could not be fully removed; rejecting the upload")
        raise PrivacyRejected("We could not remove all personal details from this document, so it was rejected "
                              "and deleted. Try uploading a version with the first page (address block) removed.")
