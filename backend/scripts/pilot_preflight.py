"""Is this deployment ready to hand an invitation link to a REAL merchant?   Exit code 1 if any check FAILs.

    python scripts/pilot_preflight.py            # checks backend/.env + the configured database
    python scripts/pilot_preflight.py --no-db    # settings only

Run it on the machine / environment the merchants will actually use, with its real environment variables.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.preflight import run_checks  # noqa: E402
from app.db.session import new_session  # noqa: E402

ICON = {"OK": "  ok ", "WARN": " warn", "FAIL": "FAIL "}


def main() -> int:
    db = None
    if "--no-db" not in sys.argv:
        try:
            db = new_session()
            db.connection()
        except Exception as e:                                                   # noqa: BLE001 - report, do not crash
            print(f"cannot reach the database: {e}")
            db = None
    results = run_checks(get_settings(), db)
    for level, name, msg in results:
        print(f"[{ICON[level]}] {name}: {msg}")
    fails = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(fails)} blocker(s), {sum(r[0] == 'WARN' for r in results)} warning(s).")
    print("NOT ready for real merchants." if fails else "No blockers. Read the warnings, then follow docs/pilot/04_operator_runbook.md.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
