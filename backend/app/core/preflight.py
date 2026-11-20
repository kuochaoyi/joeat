"""Pilot pre-flight: is this deployment safe to hand a link to a REAL merchant?

Each check returns (level, name, message). FAIL = do not invite real merchants yet; WARN = know what you are accepting; OK = fine.
Used by scripts/pilot_preflight.py (exit code 1 on any FAIL). Pure over `Settings` + a database session, so it is unit-testable.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import merchant_form
from app.core.config import Settings

WEAK_OPS_KEYS = {"dev-ops-key", "test-ops-key", "changeme", "password", "secret"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

Check = tuple[str, str, str]


def _origin(url: str) -> str:
    p = urlparse(url.strip())
    return f"{p.scheme}://{p.netloc}".lower()


def check_settings(s: Settings) -> list[Check]:
    out: list[Check] = []
    if s.allow_test_evidence:
        out.append(("FAIL", "test_evidence", "ALLOW_TEST_EVIDENCE is true: fake (demo / fixture) evidence would be shown to real users as if it were real. Set it to false."))
    else:
        out.append(("OK", "test_evidence", "ALLOW_TEST_EVIDENCE is false"))
    if not s.ops_api_key:
        out.append(("FAIL", "ops_key", "OPS_API_KEY is empty: the reviewer API is disabled, so nobody can verify merchants or publish declarations."))
    elif len(s.ops_api_key) < 16 or s.ops_api_key.lower() in WEAK_OPS_KEYS:
        out.append(("FAIL", "ops_key", "OPS_API_KEY is short or a well-known dev value. Use a random key of at least 16 characters (it is the only thing protecting /ops)."))
    else:
        out.append(("OK", "ops_key", "OPS_API_KEY is set"))
    if s.id_hash_secret == "dev-only-change-me":
        out.append(("FAIL", "id_hash_secret", "ID_HASH_SECRET is the dev default: LINE ids hashed with a public secret can be reversed by guessing. Change it (and keep it: changing it later invalidates every stored hash)."))
    else:
        out.append(("OK", "id_hash_secret", "ID_HASH_SECRET is not the dev default"))
    host = urlparse(s.frontend_url).hostname or ""
    if host in LOCAL_HOSTS or not host:
        out.append(("FAIL", "frontend_url", f"FRONTEND_URL is {s.frontend_url!r}: a merchant cannot open a localhost link. Deploy the frontend and set its public https URL."))
    elif urlparse(s.frontend_url).scheme != "https":
        out.append(("FAIL", "frontend_url", "FRONTEND_URL is not https: the invitation token travels in that page's requests. Use https."))
    else:
        out.append(("OK", "frontend_url", f"FRONTEND_URL is {s.frontend_url}"))
        if _origin(s.frontend_url) not in {_origin(o) for o in s.cors_origin_list}:
            out.append(("FAIL", "cors", "CORS_ORIGINS does not include FRONTEND_URL: the merchant page would load but every API call would be blocked by the browser."))
    if merchant_form.LEGAL_REVIEW["status"] != "approved":
        out.append(("FAIL", "legal_review", f"The merchant attestation text is not legally reviewed ({merchant_form.LEGAL_REVIEW['status']}); the form shows a 'not for production' banner. "
                                            "Have a lawyer approve the wording, then update ATTESTATION_TEXT / ATTESTATION_VERSION / LEGAL_REVIEW in app/core/merchant_form.py."))
    else:
        out.append(("OK", "legal_review", f"Attestation {merchant_form.ATTESTATION_VERSION} is marked legally approved"))
    if s.auth_mode != "line":
        out.append(("WARN", "auth_mode", "AUTH_MODE=dev: consumers can claim any identity. Acceptable for merchant-only pilot work, not for opening the consumer side to the public."))
    if s.line_dry_run:
        out.append(("WARN", "line_dry_run", "LINE_DRY_RUN=true: the bot does not reply on LINE."))
    return out


def check_database(db: Session) -> list[Check]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    out: list[Check] = []
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    current = db.scalar(text("SELECT version_num FROM alembic_version"))
    out.append(("OK", "migrations", f"database is at {current}") if current == head
               else ("FAIL", "migrations", f"database is at {current}, code expects {head}: run `alembic upgrade head`"))
    demo_claims = db.scalar(text("SELECT count(*) FROM merchant.claim WHERE is_demo"))
    fixture = db.scalar(text("SELECT count(*) FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE s.is_test AND e.declaration_id IS NOT NULL"))
    seeded = db.scalar(text("SELECT count(*) FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE s.is_test AND e.declaration_id IS NULL"))
    if demo_claims or fixture:
        out.append(("FAIL", "demo_data", f"{demo_claims} demo claim(s) and {fixture} demo-declaration evidence row(s) exist. Use a fresh database for the pilot (seed.py --reset, WITHOUT seed_demo_merchants.py)."))
    else:
        out.append(("OK", "demo_data", "no demo claims or demo declarations"))
    if seeded:
        out.append(("WARN", "seed_fixtures", f"{seeded} seed test-fixture evidence row(s) exist (hidden while ALLOW_TEST_EVIDENCE=false). Delete them before real users arrive: DELETE FROM enrichment.restaurant_attribute_evidence WHERE source_id IN (SELECT source_id FROM ref.data_source WHERE is_test)."))
    real = db.execute(text("SELECT count(*) FILTER (WHERE status = 'invited'), count(*) FILTER (WHERE status = 'verified') FROM merchant.claim WHERE NOT is_demo")).one()
    out.append(("OK", "claims", f"real claims: {real[0]} invited, {real[1]} verified"))
    open_incidents = db.scalar(text("SELECT count(*) FROM merchant.incident_report WHERE status = 'open'"))
    open_reports = db.scalar(text("SELECT count(*) FROM product.restaurant_report WHERE status = 'open'"))
    if open_incidents:
        out.append(("WARN", "open_incidents", f"{open_incidents} open incident(s): positive claims of those restaurants stay suspended until resolved"))
    if open_reports:
        out.append(("WARN", "open_reports", f"{open_reports} open user report(s) waiting for a reviewer"))
    return out


def run_checks(settings: Settings, db: Session | None) -> list[Check]:
    return check_settings(settings) + (check_database(db) if db is not None else [("WARN", "database", "database not checked")])
