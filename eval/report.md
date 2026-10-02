# BondCheck evaluation report

*Generated 2026-10-02 09:51 UTC · engine: **offline rule engine** · 50 synthetic letters (45 processed, 5 scanned skipped: no OCR)*

## Single-pass extraction vs the agentic loop

| | Single-pass extraction | Agentic (self-check + re-read) | Agentic + uploader confirmation |
|---|---|---|---|
| Field accuracy | 88.5% | 99.6% | 100.0% |
| Hallucinated fields | 22 | 0 | — |
| Avg time per letter | — | 0.011 s | — |
| Avg tokens per letter | — | 0 | — |

Uploader questions: 2 across 2 letters.

## Targets

| Metric | Target | Result |
|---|---|---|
| Field-level extraction accuracy | ≥ 90% | 99.6% |
| PII leak rate (personal data in stored records) | 0% | 0.0% |
| Hallucinated values stored | 0% | 0.0% |
| Conflict detection precision / recall | ≥ 85% | 100.0% / 100.0% |
| Q&A answers with correct citations | ≥ 95% | 100.0% |
| Average cost and time per upload | measured | 0 tokens, 0.011 s |

## Privacy

- PII items planted: 335
- Leaked into stored evidence: 0
- Still present anywhere in the redacted text: 0 (0.0%)
- Re-scan attempts needed: {1: 28, 2: 17}

## Where errors remain

- Single-pass: {'bond_months': 36, 'certificates_retained': 12, 'ctc_annual': 9, 'has_bond': 5}
- Agentic: {'bond_months': 2}

> **Caveat:** the test letters come from the same generator the extraction rules were developed against (different random seeds). Treat these as an upper bound and add real, consented letters to the test set before quoting the numbers.

> These numbers come from the offline rule engine. Set `ANTHROPIC_API_KEY` and re-run `python -m eval.run_eval` to measure the Claude-based extraction (and OCR for the scanned letters).
