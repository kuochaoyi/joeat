"""Start an embedded PostgreSQL for local development (no Docker / system PostgreSQL needed).

    python scripts/dev_postgres.py          # start (idempotent), create database 'joeat', write DATABASE_URL to backend/.env
    python scripts/dev_postgres.py --stop   # stop it

Uses the `pgserver` package (dev dependency). For a real deployment use PostgreSQL 14+ (see docker/docker-compose.yml).
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pgserver
import psycopg

BACKEND = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND / ".pgdata"
ENV_FILE = BACKEND / ".env"
DB_NAME = "joeat"


def write_env(url: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith("DATABASE_URL=")]
    lines.insert(0, f"DATABASE_URL={url}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    server = pgserver.get_server(str(DATA_DIR), cleanup_mode=None)
    if args.stop:
        server.cleanup()
        print("embedded PostgreSQL stopped")
        return 0
    admin_uri = server.get_uri()                      # postgresql://postgres:@127.0.0.1:PORT/postgres
    with psycopg.connect(admin_uri, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {DB_NAME} ENCODING 'UTF8' TEMPLATE template0")
    parts = urlsplit(admin_uri)
    url = urlunsplit(("postgresql+psycopg", parts.netloc, f"/{DB_NAME}", parts.query, parts.fragment))
    write_env(url)
    print("embedded PostgreSQL is running")
    print("DATABASE_URL =", url, "(written to backend/.env)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
