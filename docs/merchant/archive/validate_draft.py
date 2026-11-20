"""Validate draft_0003_merchant_declaration.sql on a REAL PostgreSQL, including the recommendation engine.

    cd joeat/backend && .venv/Scripts/python -X utf8 ../docs/merchant/validate_draft.py

Builds a scratch database (migrations 0001+0002, seeds, then the draft), runs the scenarios below and prints PASS/FAIL per check.
Uses the embedded PostgreSQL of scripts/dev_postgres.py (backend/.pgdata); it creates and drops its own database.
"""
import os
import re
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
import pgserver

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

DB = "joeat_merchant_draft"
server = pgserver.get_server(str(BACKEND / ".pgdata"), cleanup_mode=None)
admin_uri = server.get_uri()
m = re.match(r"postgresql://([^:@/]+)(?::[^@]*)?@([^/]+)/", admin_uri)
DSN = f"postgresql://{m.group(1)}@{m.group(2)}/{DB}"
URL = f"postgresql+psycopg://{m.group(1)}@{m.group(2)}/{DB}"
with psycopg.connect(admin_uri, autocommit=True) as c:
    c.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    c.execute(f"CREATE DATABASE \"{DB}\" ENCODING 'UTF8' TEMPLATE template0")
os.environ["DATABASE_URL"] = URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

cfg = Config(str(BACKEND / "alembic.ini"))
cfg.set_main_option("script_location", str(BACKEND / "alembic"))
command.upgrade(cfg, "0002")        # the draft is applied by hand on top of 0002; it has been superseded by migration 0003 (backend/app/db/sql/0003_merchant_declaration.sql)
con = psycopg.connect(DSN, autocommit=True)
for f in sorted((BACKEND.parent / "data" / "seed").glob("*.sql")):
    con.execute(f.read_text(encoding="utf-8"))
con.execute((HERE / "draft_0003_merchant_declaration.sql").read_text(encoding="utf-8"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

client = TestClient(create_app())
results: list[tuple[bool, str, str]] = []
TODAY = con.execute("SELECT ref.today_tpe()").fetchone()[0]


def check(name: str, cond: bool, detail: str = ""):
    results.append((bool(cond), name, "" if cond else detail))


def fails(name: str, sql: str, args=None, expect_in: str | None = None):
    """The statement must be rejected by the database."""
    try:
        con.execute(sql, args)
        check(name, False, "ACCEPTED (should have been rejected)")
    except psycopg.Error as e:
        msg = str(e).splitlines()[0]
        check(name, expect_in is None or expect_in in msg, "rejected, but for another reason: " + msg[:120])


def rid(name: str):
    return con.execute("SELECT restaurant_id FROM identity.restaurant WHERE canonical_name = %s", (name,)).fetchone()[0]


def new_claim(restaurant, level="strong", method="phone_callback", role="owner", verified=True):
    token = uuid.uuid4().hex
    cid = con.execute("INSERT INTO merchant.claim (restaurant_id, token_hash, invited_by) VALUES (%s, %s, 'operator-1') RETURNING claim_id", (restaurant, token)).fetchone()[0]
    if verified:
        con.execute("UPDATE merchant.claim SET status='verified', verification_method=%s, verification_level=%s, verified_by='operator-1', verified_at=now(), claimant_role=%s WHERE claim_id=%s",
                    (method, level, role, cid))
    return cid


def declare(claim, answers: dict, menu_url=None, valid_days=90, submit=True):
    d = con.execute("SELECT merchant.start_declaration(%s, %s)", (claim, valid_days)).fetchone()[0]
    for attr, ans in answers.items():
        kw = {}
        if isinstance(ans, tuple):
            ans, kw = ans
        con.execute("UPDATE merchant.declaration_item SET answer=%s, cross_contact=%s, certificate_ref=%s, note=%s WHERE declaration_id=%s AND attribute_code=%s",
                    (ans, kw.get("cross", "not_sure"), kw.get("cert"), kw.get("note"), d, attr))
    if menu_url:
        con.execute("UPDATE merchant.declaration SET menu_url=%s WHERE declaration_id=%s", (menu_url, d))
    if submit:
        con.execute("SELECT merchant.submit_declaration(%s, 'owner', %s, 'attest-v1')", (d, TODAY))
    return d


def state(restaurant, attr):
    r = con.execute("SELECT state::text FROM enrichment.restaurant_attribute_state WHERE restaurant_id=%s AND attribute_code=%s", (restaurant, attr)).fetchone()
    return r[0] if r else "UNKNOWN"


def engine(restaurant_name: str, attr: str, reason="allergy"):
    """One participant with a hard constraint -> run the real recommendation service -> the stored check row for that restaurant."""
    sid = client.post("/sessions", json={"title": "v", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "v-" + uuid.uuid4().hex}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": attr, "reason": reason}]})
    client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}, {"cuisine_tag": "小吃", "stance": "love"}]})
    resp = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True})
    assert resp.status_code == 201, resp.text
    run = resp.json()["run_id"]
    row = con.execute("SELECT evidence_state::text, action, warning_level, may_show_safe_badge, evidence_snapshot->>'basis' FROM product.recommendation_constraint_check k "
                      "JOIN identity.restaurant r USING (restaurant_id) WHERE k.run_id = %s AND r.canonical_name = %s", (run, restaurant_name)).fetchone()
    return row, resp.json()


duck, guo, gangyuan = rid("鴨肉珍"), rid("郭家肉粽"), rid("港園牛肉麵")

# ---------------------------------------------------------------- A. a claim must be real before anything is declared
c_open = new_claim(duck, verified=False)
fails("A1 an invited (unverified) claim cannot start a declaration", "SELECT merchant.start_declaration(%s)", (c_open,), "only a verified claim")
fails("A2 'verified' without a method / verifier is rejected", "UPDATE merchant.claim SET status='verified' WHERE claim_id=%s", (c_open,), "claim_verified_needs_proof")
fails("A3 'strong' via a channel message is rejected (strong needs a callback or a visit)",
      "UPDATE merchant.claim SET status='verified', verification_method='official_channel_message', verification_level='strong', verified_by='o', verified_at=now() WHERE claim_id=%s", (c_open,), "claim_strong_methods")
c_other = new_claim(guo)
fails("A4 a claim cannot declare for another restaurant",
      "INSERT INTO merchant.declaration (claim_id, restaurant_id) VALUES (%s, %s)", (c_other, duck), "decl_claim_fk")

# ---------------------------------------------------------------- B. a weakly verified claim can never produce CONFIRMED_*
c_basic = new_claim(duck, level="basic", method="official_channel_message")
d1 = declare(c_basic, {"peanut": ("absent_entire_menu", {"cross": "possible", "note": "共用炒鍋"}), "vegetarian": "offered"})
n = con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d1,)).fetchone()[0]
check("B1 basic-level absence -> LIKELY_ABSENT (never CONFIRMED)", state(duck, "peanut") == "LIKELY_ABSENT" and n == 2, state(duck, "peanut"))
row, _ = engine("鴨肉珍", "peanut")
check("B2 engine: LIKELY_ABSENT on a critical allergen = WARN critical, no safe badge", row[:4] == ("LIKELY_ABSENT", "WARN", "critical", False), str(row))
ev = con.execute("SELECT evidence_basis, confidence, valid_until - last_verified_at, evidence_text FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id=%s AND attribute_code='peanut' AND declaration_id=%s", (duck, d1)).fetchone()
check("B3 evidence carries basis, MEDIUM confidence, 90-day validity, cross-contact note", ev[:3] == ("restaurant_declaration", "MEDIUM", 90) and "共用設備：可能" in ev[3] and "共用炒鍋" in ev[3], str(ev))
check("B4 declaration became approved and an audit trail exists", con.execute("SELECT status FROM merchant.declaration WHERE declaration_id=%s", (d1,)).fetchone()[0] == "approved"
      and con.execute("SELECT count(*) FROM merchant.declaration_audit WHERE declaration_id=%s", (d1,)).fetchone()[0] >= 3)

# ---------------------------------------------------------------- C. a strongly verified claim with a menu can produce CONFIRMED_ABSENT
c_strong = new_claim(duck)
d2 = declare(c_strong, {"peanut": "absent_entire_menu", "tree_nut": "absent_entire_menu", "seafood": "present_in_some_dishes", "vegetarian": "not_offered"}, menu_url="https://example.invalid/menu.pdf")
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d2,))
check("C1 strong + menu -> CONFIRMED_ABSENT with official_menu basis", state(duck, "peanut") == "CONFIRMED_ABSENT" and
      con.execute("SELECT evidence_basis, confidence FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id=%s AND attribute_code='peanut' AND declaration_id=%s", (duck, d2)).fetchone() == ("official_menu", "HIGH"))
row, resp = engine("鴨肉珍", "peanut")
check("C2 engine: CONFIRMED_ABSENT -> PASS with a safe badge, citing the first-party basis", row == ("CONFIRMED_ABSENT", "PASS", "none", True, "official_menu"), str(row))
card = next((t for t in resp["top3"] if t["name"] == "鴨肉珍"), None)
check("C3 API card shows the confirmed attribute (when the restaurant is in the Top 3)", card is None or (card["hard_constraint"]["confirmed_safe"] == ["花生"] and "花生" not in card["hard_constraint"]["unknown_attributes"]), str(card and card["hard_constraint"]))
check("C4 the earlier basic-level claim was retired by the new declaration", con.execute("SELECT status FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id=%s AND declaration_id=%s AND attribute_code='peanut'", (duck, d1)).fetchone()[0] == "superseded")
check("C5 seafood 'present in some dishes' -> CONFIRMED_PRESENT (coarse by design: the restaurant is excluded for seafood avoiders)", state(duck, "seafood") == "CONFIRMED_PRESENT")
row, _ = engine("鴨肉珍", "seafood", reason="dislike")
check("C6 engine: that presence claim excludes the restaurant for a seafood avoider", row[:2] == ("CONFIRMED_PRESENT", "EXCLUDE"), str(row))
check("C7 require-type 'not_offered' -> CONFIRMED_ABSENT (a vegetarian is excluded)", state(duck, "vegetarian") == "CONFIRMED_ABSENT")

# ---------------------------------------------------------------- D. contradictions are never resolved silently
d3 = declare(new_claim(guo), {"peanut": "absent_entire_menu"})
fails("D1 declaring 'no peanut' against third-party 'peanut zongzi' evidence is blocked", "SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d3,), "contradiction with existing evidence")
check("D2 ... and nothing changed (still LIKELY_PRESENT, declaration still 'submitted')", state(guo, "peanut") == "LIKELY_PRESENT" and
      con.execute("SELECT status FROM merchant.declaration WHERE declaration_id=%s", (d3,)).fetchone()[0] == "submitted")
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-2', true)", (d3,))
check("D3 a named reviewer can supersede LIKELY_* evidence explicitly -> CONFIRMED_ABSENT", state(guo, "peanut") == "CONFIRMED_ABSENT")
check("D4 the superseded row points at its replacement and the override is audited",
      con.execute("SELECT count(*) FROM enrichment.restaurant_attribute_evidence e JOIN enrichment.restaurant_attribute_evidence n ON n.evidence_id = e.superseded_by WHERE e.restaurant_id=%s AND e.attribute_code='peanut' AND e.status='superseded' AND n.declaration_id=%s", (guo, d3)).fetchone()[0] == 1
      and con.execute("SELECT actor FROM merchant.declaration_audit WHERE declaration_id=%s AND event='superseded_third_party_evidence'", (d3,)).fetchone()[0] == "reviewer-2")
d4 = declare(new_claim(gangyuan), {"beef": "absent_entire_menu"})
fails("D5 a declaration can never override CONFIRMED_PRESENT evidence (restaurant name 牛肉麵), even with p_supersede", "SELECT merchant.publish_declaration(%s, 'reviewer-2', true)", (d4,), "contradiction with CONFIRMED evidence")
check("D6 beef is still CONFIRMED_PRESENT", state(gangyuan, "beef") == "CONFIRMED_PRESENT")

# ---------------------------------------------------------------- E. the database refuses bad declarations
d5 = declare(new_claim(duck), {}, submit=False)
fails("E1 'offered' is not a valid answer for an avoid-type attribute", "UPDATE merchant.declaration_item SET answer='offered' WHERE declaration_id=%s AND attribute_code='peanut'", (d5,), "not valid for avoid-type")
fails("E2 'absent_entire_menu' is not valid for a require-type attribute", "UPDATE merchant.declaration_item SET answer='absent_entire_menu' WHERE declaration_id=%s AND attribute_code='vegan'", (d5,), "not valid for require-type")
check("E3 every attribute starts as not_sure (silence stays UNKNOWN)", con.execute("SELECT count(*), count(*) FILTER (WHERE answer='not_sure') FROM merchant.declaration_item WHERE declaration_id=%s", (d5,)).fetchone() == (17, 17))
fails("E4 a menu date in the future is rejected", "SELECT merchant.submit_declaration(%s, 'owner', %s, 'v1')", (d5, TODAY + timedelta(days=1)), "menu_as_of")
fails("E5 a menu older than 180 days is rejected", "SELECT merchant.submit_declaration(%s, 'owner', %s, 'v1')", (d5, TODAY - timedelta(days=181)), "menu_as_of")
fails("E6 valid_days above 180 is rejected", "UPDATE merchant.declaration SET valid_days = 181 WHERE declaration_id=%s", (d5,), "valid_days")
fails("E7 publishing a draft (not submitted) is rejected", "SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d5,), "only a submitted")
fails("E8 publishing without a named reviewer is rejected", "SELECT merchant.publish_declaration(%s, '')", (d4,), "named reviewer")
fails("E9 an approved declaration's items are frozen", "UPDATE merchant.declaration_item SET answer='not_sure' WHERE declaration_id=%s AND attribute_code='peanut'", (d2,), "frozen")
fails("E10 an approved declaration cannot be deleted (history is kept)", "DELETE FROM merchant.declaration WHERE declaration_id=%s", (d2,), "only draft")
fails("E11 the audit log is append-only", "DELETE FROM merchant.declaration_audit WHERE declaration_id=%s", (d2,), "append-only")
fails("E12 'approved' without attestation / reviewer is rejected", "UPDATE merchant.declaration SET status='approved' WHERE declaration_id=%s", (d5,), "violates check constraint")
fails("E13 an invalid answer value is rejected", "UPDATE merchant.declaration_item SET answer='definitely' WHERE declaration_id=%s AND attribute_code='peanut'", (d5,), "answer")
fails("E14 even a draft cannot be deleted once the audit trail exists (history is kept; withdraw it instead)", "DELETE FROM merchant.declaration WHERE declaration_id=%s", (d5,), "audit")
d6 = declare(c_strong, {"halal": "offered"}, valid_days=30)
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d6,))
check("E15 halal 'offered' without a certificate stays LIKELY_PRESENT even for a strong claim", state(duck, "halal") == "LIKELY_PRESENT", state(duck, "halal"))
d6b = declare(c_strong, {"halal": ("offered", {"cert": "HALAL-0001"})})
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d6b,))
check("E16 ... and CONFIRMED_PRESENT once a certificate reference is given", state(duck, "halal") == "CONFIRMED_PRESENT", state(duck, "halal"))

# ---------------------------------------------------------------- F. a new declaration replaces the old one; silence is not carried over
d7 = declare(c_strong, {"tree_nut": "absent_entire_menu"}, menu_url="https://example.invalid/menu.pdf")     # peanut is now not_sure
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d7,))
check("F1 peanut left as not_sure in the new declaration -> the old CONFIRMED_ABSENT is retired -> UNKNOWN", state(duck, "peanut") == "UNKNOWN", state(duck, "peanut"))
check("F2 tree_nut re-asserted: same evidence row renewed, not duplicated", con.execute("SELECT count(*) FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id=%s AND attribute_code='tree_nut' AND source_id=6 AND evidence_basis='official_menu'", (duck,)).fetchone()[0] == 1
      and state(duck, "tree_nut") == "CONFIRMED_ABSENT")
# each declaration is a COMPLETE snapshot: whatever it does not re-assert falls back to UNKNOWN
d8 = declare(c_strong, {"peanut": "absent_entire_menu", "tree_nut": "absent_entire_menu", "seafood": "present_in_some_dishes"}, menu_url="https://example.invalid/menu2.pdf")
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d8,))
check("F3 a complete re-declaration restores peanut / tree_nut CONFIRMED_ABSENT and seafood CONFIRMED_PRESENT",
      (state(duck, "peanut"), state(duck, "tree_nut"), state(duck, "seafood")) == ("CONFIRMED_ABSENT", "CONFIRMED_ABSENT", "CONFIRMED_PRESENT"), f"{state(duck,'peanut')} {state(duck,'tree_nut')} {state(duck,'seafood')}")

# ---------------------------------------------------------------- G. kill switch
con.execute("INSERT INTO merchant.incident_report (restaurant_id, severity, description) VALUES (%s, 'allergic_reaction', 'customer reported a reaction') RETURNING incident_id", (duck,))
inc = con.execute("SELECT max(incident_id) FROM merchant.incident_report").fetchone()[0]
check("G1 an allergic-reaction report suspends the restaurant's positive claims immediately", state(duck, "peanut") == "UNKNOWN" and state(duck, "tree_nut") == "UNKNOWN", f"{state(duck,'peanut')} {state(duck,'tree_nut')}")
check("G2 ... but a 'contains X' claim is NOT suspended (that would make the venue look safer)", state(duck, "seafood") == "CONFIRMED_PRESENT", state(duck, "seafood"))
row, _ = engine("鴨肉珍", "peanut")
check("G3 engine: back to WARN critical while the incident is open", row[:3] == ("UNKNOWN", "WARN", "critical"), str(row))
con.execute("SELECT merchant.resolve_incident(%s, 'dismissed', 'reviewer-3')", (inc,))
check("G4 dismissing the incident reinstates the claims", state(duck, "peanut") == "CONFIRMED_ABSENT" and state(duck, "tree_nut") == "CONFIRMED_ABSENT")
con.execute("INSERT INTO merchant.incident_report (restaurant_id, attribute_code, severity) VALUES (%s, 'peanut', 'wrong_info')", (duck,))
inc2 = con.execute("SELECT max(incident_id) FROM merchant.incident_report").fetchone()[0]
check("G5 a wrong_info report for one attribute suspends only that attribute", state(duck, "peanut") == "UNKNOWN" and state(duck, "tree_nut") == "CONFIRMED_ABSENT")
con.execute("SELECT merchant.resolve_incident(%s, 'confirmed', 'reviewer-3')", (inc2,))
check("G6 a confirmed incident retires the claim and revokes the restaurant's verified claims", state(duck, "peanut") == "UNKNOWN" and
      con.execute("SELECT count(*) FROM merchant.claim WHERE restaurant_id=%s AND status='verified'", (duck,)).fetchone()[0] == 0)
fails("G7 an incident cannot be resolved twice", "SELECT merchant.resolve_incident(%s, 'dismissed', 'x')", (inc2,), "not open")

# ---------------------------------------------------------------- H. expiry and the existing safety rules still hold
c_new = new_claim(duck)
d9 = declare(c_new, {"egg": "absent_entire_menu"}, menu_url="https://example.invalid/m.pdf")
con.execute("SELECT merchant.publish_declaration(%s, 'reviewer-1')", (d9,))
check("H1 egg CONFIRMED_ABSENT is visible", state(duck, "egg") == "CONFIRMED_ABSENT")
egg_rows = con.execute("SELECT count(*) FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id=%s AND attribute_code='egg' AND declaration_id=%s AND status='active'", (duck, d9)).fetchone()[0]
check("H3a (precondition) the egg evidence row exists and is active", egg_rows == 1)
fails("H3 the original evidence rule still blocks CONFIRMED_ABSENT beyond 180 days", "UPDATE enrichment.restaurant_attribute_evidence SET valid_until = last_verified_at + 181 WHERE restaurant_id=%s AND attribute_code='egg' AND declaration_id=%s", (duck, d9), "evidence_absence_expires")
con.execute("UPDATE enrichment.restaurant_attribute_evidence SET observed_at = %s, last_verified_at = %s, valid_until = %s WHERE restaurant_id=%s AND attribute_code='egg' AND declaration_id=%s",
            (TODAY - timedelta(days=100), TODAY - timedelta(days=100), TODAY - timedelta(days=10), duck, d9))
check("H2 once valid_until has passed the claim disappears on its own (=> UNKNOWN)", state(duck, "egg") == "UNKNOWN")
check("H4 the 3 test-fixture claims remain hidden", con.execute("SELECT count(*) FROM enrichment.restaurant_attribute_state s JOIN enrichment.restaurant_attribute_evidence e ON e.evidence_id = s.deciding_evidence_id WHERE e.source_id = 7").fetchone()[0] == 0)

# ---------------------------------------------------------------- report
ok = sum(1 for r in results if r[0])
print(f"RESULT: {ok} passed, {len(results) - ok} failed\n")
for passed, name, detail in results:
    print(("PASS " if passed else "FAIL ") + name + ("" if passed else "   <-- " + detail))
con.close()
with psycopg.connect(admin_uri, autocommit=True) as c:
    c.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
sys.exit(0 if ok == len(results) else 1)
