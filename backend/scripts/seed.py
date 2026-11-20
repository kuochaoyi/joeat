"""Load the reference data and the Yancheng seed restaurants.

    python scripts/seed.py                    # seed an empty database (no-op if restaurants already exist)
    python scripts/seed.py --reset            # drop everything, re-run migrations, seed again
    python scripts/seed.py --pool all         # DEMO ONLY: mark every seed restaurant in_pool (see warning)
    python scripts/seed.py --reset --no-fixtures   # PILOT database: real data only, no fake evidence (refuses to wipe real merchant claims)

Seed files (repo-root data/seed, applied in order):
  01_attribute_seed.sql        evidence states, 17 attributes, 30 decision rules, scoring config v1
  02_seed_restaurants.sql      30 real PoC restaurants + evidence (+ 3 hidden test-fixture claims)
  03_seed_extra_hotpot.sql     one more real restaurant (hotpot) corroborated by tax registry + web mention
By default only restaurants corroborated by a second source are in_pool (15 of 31).
"""
import argparse
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.config import get_settings  # noqa: E402

SEED_DIR = BACKEND.parent / "data" / "seed"


def dsn() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


def alembic_cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="downgrade to base, upgrade to head, then seed")
    ap.add_argument("--pool", choices=["corroborated", "all"], default="corroborated")
    ap.add_argument("--no-fixtures", action="store_true", help="PILOT: remove the hidden test-fixture evidence after seeding (real third-party evidence stays)")
    ap.add_argument("--destroy-real-data", action="store_true", help="allow --reset even when real (non-demo) merchant claims exist: they are deleted for good")
    args = ap.parse_args()

    if args.reset:
        with psycopg.connect(dsn(), autocommit=True) as conn:
            try:
                real = conn.execute("SELECT count(*) FROM merchant.claim WHERE NOT is_demo").fetchone()[0]
            except psycopg.errors.UndefinedTable:                                 # fresh / older database: nothing to protect
                real = 0
        if real and not args.destroy_real_data:
            print(f"refusing --reset: {real} real merchant claim(s) exist and would be deleted (declarations, verification records, audit trail). "
                  "Back up first, then pass --destroy-real-data if you really mean it.")
            return 2
        command.downgrade(alembic_cfg(), "base")
    command.upgrade(alembic_cfg(), "head")

    with psycopg.connect(dsn(), autocommit=True) as conn:
        n = conn.execute("SELECT count(*) FROM identity.restaurant").fetchone()[0]
        if n and not args.reset:
            print(f"database already has {n} restaurants; use --reset to reseed")
            return 0
        for f in sorted(SEED_DIR.glob("*.sql")):
            print("applying", f.name)
            conn.execute(f.read_text(encoding="utf-8"))
        if args.pool == "all":
            conn.execute("UPDATE identity.restaurant SET pool_status = 'in_pool', pool_reason = 'DEMO: forced into pool' WHERE pool_status = 'candidate'")
            print("WARNING: --pool all marks single-source, unverified restaurants as in_pool. Demo only.")
        if args.no_fixtures:
            gone = conn.execute("DELETE FROM enrichment.restaurant_attribute_evidence WHERE source_id IN (SELECT source_id FROM ref.data_source WHERE is_test)").rowcount
            print(f"removed {gone} test-fixture evidence row(s) (pilot database: no fake evidence)")
        rows = conn.execute("SELECT pool_status, count(*) FROM identity.restaurant GROUP BY 1 ORDER BY 1").fetchall()
        print("restaurants by pool_status:", dict(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
