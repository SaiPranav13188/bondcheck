import os
import sys
import tempfile
from pathlib import Path

# Isolated SQLite database and offline engine for every test run (set before any project import).
_tmp = Path(tempfile.mkdtemp())
os.environ["SQLITE_PATH"] = str(_tmp / "test.db")
os.environ["BONDCHECK_OFFLINE"] = "1"
# TEST_DATABASE_URL runs the whole suite against PostgreSQL instead of SQLite.
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def seeded_db():
    from db.seed import seed

    seed(verbose=False)
    return True
