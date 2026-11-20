"""FAKE merchant data for developing and demoing the self-declaration system.  EVERYTHING THIS SCRIPT CREATES IS DEMO DATA.

    ALLOW_TEST_EVIDENCE=true python scripts/seed_demo_merchants.py

* Claims are marked is_demo, so what they publish goes into the hidden TEST source (never the real first-party source).
* It refuses to run unless ALLOW_TEST_EVIDENCE is true, and the tokens are deliberately guessable ("demo-..."): never run it against production.
* Run it once per database. Declarations are never deleted (history is kept), so to start over: `python scripts/seed.py --reset`.
* The restaurants are the real PoC restaurants; the *claims, answers and incidents* are invented.
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import new_session  # noqa: E402
from app.services import merchant as svc  # noqa: E402

ACTOR, REVIEWER = "demo-seed", "demo-reviewer"
NOTE = "DEMO: 示範資料，並非真實驗證"
MENU = "https://example.invalid/demo-menu.pdf"

# (token, restaurant, verification method or None, claimant role, scenario)
SCENARIOS = [
    ("demo-duck", "鴨肉珍", "phone_callback", "owner", "verified, nothing declared yet: open the link and fill the form"),
    ("demo-borage", "The Borage 琉璃苣", None, None, "invited but NOT verified: the merchant must wait; the reviewer must verify"),
    ("demo-ayin", "阿英排骨飯", "onsite_visit", "manager", "submitted, clean: ready to publish"),
    ("demo-guo", "郭家肉粽", "phone_callback", "owner", "submitted, CONTRADICTS third-party evidence (peanut zongzi)"),
    ("demo-tian", "田記豆漿", "official_channel_message", "staff", "basic verification: its absence claims can only be 'possible'"),
    ("demo-jiu", "九記 鹽埕食糖水", "phone_callback", "owner", "sent back for more information"),
    ("demo-dagou", "大溝頂虱目魚米粉湯", "official_menu_review", "owner", "already published (visible to the engine in demo mode)"),
    ("demo-laocai", "老蔡虱目魚粥", "phone_callback", "owner", "published, then a reaction was reported: claims suspended, incident open"),
]


def main() -> int:
    if not get_settings().allow_test_evidence:
        print("refusing: set ALLOW_TEST_EVIDENCE=true (demo data publishes fake evidence into the hidden test source). Never do this in production.")
        return 1
    db = new_session()
    if db.execute(text("SELECT 1 FROM merchant.claim WHERE is_demo LIMIT 1")).first():
        print("demo merchants already exist in this database; run `python scripts/seed.py --reset` to start over")
        return 0
    today = db.execute(text("SELECT ref.today_tpe()")).scalar()
    claims: dict[str, int] = {}
    for token, name, method, role, _ in SCENARIOS:
        rid = db.execute(text("SELECT restaurant_id FROM identity.restaurant WHERE canonical_name = :n"), {"n": name}).scalar()
        if rid is None:
            raise SystemExit(f"restaurant {name} not found: run scripts/seed.py first")
        cid = svc.run(db, ACTOR, lambda: db.execute(text(
            "INSERT INTO merchant.claim (restaurant_id, token_hash, invited_by, is_demo) VALUES (:r, :h, :a, TRUE) RETURNING claim_id"),
            {"r": rid, "h": svc.hash_token(token), "a": ACTOR}).scalar())
        claims[token] = cid
        if method:
            svc.verify_claim(db, REVIEWER, cid, method, NOTE, role)

    def declare(token, answers, *, menu=None, submit=True):
        d = svc.start_declaration(db, ACTOR, claims[token])
        for attr, (ans, cc, *rest) in answers.items():
            svc.set_item(db, ACTOR, d, attr, ans, cross_contact_status=cc, note=rest[0] if rest else None)
        if menu:
            svc.set_menu(db, ACTOR, d, menu)
        if submit:
            svc.submit_declaration(db, ACTOR, d, "owner", today - timedelta(days=3), "attest-v0-draft")
        return d

    declare("demo-ayin", {"sesame": ("absent_entire_menu", "confirmed_none", "專用炸鍋"), "soy": ("absent_entire_menu", "possible"), "pork": ("present_in_most_dishes", "unknown")}, menu=MENU)
    declare("demo-guo", {"peanut": ("absent_entire_menu", "confirmed_none"), "pork": ("present_in_most_dishes", "unknown")}, menu=MENU)
    declare("demo-tian", {"egg": ("absent_entire_menu", "confirmed_none"), "vegetarian": ("offered", "unknown")})
    d_jiu = declare("demo-jiu", {"tree_nut": ("absent_entire_menu", "confirmed_none"), "sesame": ("absent_entire_menu", "unknown")})
    svc.review(db, REVIEWER, d_jiu, "needs_info", "DEMO: 請附上最新菜單連結")
    d = declare("demo-dagou", {"milk": ("absent_entire_menu", "confirmed_none"), "seafood": ("present_in_most_dishes", "unknown")}, menu=MENU)
    svc.publish(db, REVIEWER, d, False)
    d = declare("demo-laocai", {"egg": ("absent_entire_menu", "confirmed_none")}, menu=MENU)
    svc.publish(db, REVIEWER, d, False)
    rid = db.execute(text("SELECT restaurant_id FROM merchant.claim WHERE claim_id = :c"), {"c": claims["demo-laocai"]}).scalar()
    svc.create_incident(db, REVIEWER, rid, "allergic_reaction", None, "DEMO: 示範用的假通報")

    base = "http://localhost:3000"
    print("DEMO merchants created (all fake). Merchant links:")
    for token, name, _, _, what in SCENARIOS:
        print(f"  {base}/m/{token}   {name}: {what}")
    print(f"\nReviewer console: {base}/ops   (needs OPS_API_KEY in backend/.env; use any name)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
