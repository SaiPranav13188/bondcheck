"""Central settings, read once from the environment (.env supported)."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Database: PostgreSQL when DATABASE_URL is set (Neon/Supabase), otherwise local SQLite.
    database_url: str = os.getenv("DATABASE_URL", "")
    # The Q&A agent's read-only role. Falls back to the main URL (still forced read-only per query).
    readonly_database_url: str = os.getenv("DATABASE_URL_READONLY", "")
    sqlite_path: Path = Path(os.getenv("SQLITE_PATH", str(DATA_DIR / "bondcheck.db")))

    # LLM. Offline mode uses the deterministic rule engine so the whole system runs without a key.
    offline: bool = _bool("BONDCHECK_OFFLINE") or not (
        os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    )
    fast_model: str = os.getenv("BONDCHECK_FAST_MODEL", "claude-haiku-4-5")      # classification, PII checks
    strong_model: str = os.getenv("BONDCHECK_STRONG_MODEL", "claude-sonnet-5-5")  # extraction, Q&A, research

    # Orchestrator guardrails
    max_retries: int = int(os.getenv("BONDCHECK_MAX_RETRIES", "2"))
    token_budget: int = int(os.getenv("BONDCHECK_TOKEN_BUDGET", "80000"))
    privacy_max_attempts: int = 3
    extraction_max_rereads: int = 2
    confidence_threshold: float = float(os.getenv("BONDCHECK_CONFIDENCE_THRESHOLD", "0.75"))

    # Read-only SQL guardrails
    sql_row_limit: int = 200
    sql_timeout_ms: int = 5000

    # Outlier thresholds (Verification Agent)
    outlier_penalty: int = 1_000_000       # ₹10,00,000
    outlier_bond_months: int = 60

    # Admin / cron / email
    admin_token: str = os.getenv("ADMIN_TOKEN", "dev-admin-token")
    cron_secret: str = os.getenv("CRON_SECRET", "dev-cron-secret")
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    alert_from: str = os.getenv("ALERT_FROM_EMAIL", "BondCheck <alerts@bondcheck.dev>")
    site_url: str = os.getenv("SITE_URL", "http://localhost:3000")
    # Any Vercel deployment of the frontend (production and preview URLs).
    cors_origin_regex: str = os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    )

    @property
    def use_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://"))

    @property
    def tesseract_available(self) -> bool:
        return shutil.which(os.getenv("TESSERACT_CMD", "tesseract")) is not None


settings = Settings()
