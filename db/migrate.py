"""Create or upgrade the schema, and optionally seed demo data into an empty database.

    python -m db.migrate                  # schema only (idempotent, safe to run any time)
    python -m db.migrate --seed-if-empty  # also seed ~70 demo letters through the agents if there are no companies

Run once per deploy as the Kubernetes `bondcheck-migrate` Job, before the API pods take traffic.
The API pods also run the (idempotent, advisory-locked) schema step at startup, so the order is not critical.
"""
from __future__ import annotations

import argparse
import logging
import sys

from tools import database as db


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed-if-empty", action="store_true", help="seed demo data when the database has no companies")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log = logging.getLogger("bondcheck.migrate")

    try:
        db.init_db()
    except db.DatabaseUnreachable as e:
        log.error("%s", e)
        return 1
    log.info("schema is up to date (%s)", "postgres" if db.settings.use_postgres else "sqlite")

    if args.seed_if_empty and db.is_empty():
        from db.seed import seed

        log.info("database is empty: seeding demo data through the agent pipeline")
        stats = seed(verbose=False)
        log.info("seeded: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
