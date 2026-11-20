"""Run the fixed demo ("高中同學聚餐": A no beef + Japanese, B peanut allergy + hotpot, C anything) end to end.

    python scripts/demo.py                          # against a running server (default http://localhost:8000)
    python scripts/demo.py --base-url http://host   # another server
    python scripts/demo.py --in-process             # no server needed; uses the FastAPI app directly (database must be migrated + seeded)
Re-running creates a new session each time (new demo users), so it is safe to repeat.
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo_scenario import render, run_demo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--in-process", action="store_true")
    args = ap.parse_args()
    if args.in_process:
        from fastapi.testclient import TestClient

        from app.main import app
        client = TestClient(app)
    else:
        import httpx
        client = httpx.Client(base_url=args.base_url, timeout=30)
    demo = run_demo(client, user_prefix=f"demo-{uuid.uuid4().hex[:8]}")
    print(render(demo))
    print("\nsession_id:", demo["session"]["session_id"])
    print("open the web UI at: /s/" + demo["session"]["session_id"] + "/results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
