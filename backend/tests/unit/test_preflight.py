"""Pilot pre-flight: every unsafe configuration is a FAIL, a correct one is not. Pure over Settings (no database)."""
import pytest

from app.core import merchant_form
from app.core.config import Settings
from app.core.preflight import check_settings

GOOD = dict(allow_test_evidence=False, ops_api_key="k" * 24, id_hash_secret="a-real-secret", frontend_url="https://joeat.example.org",
            cors_origins="https://joeat.example.org", auth_mode="line", line_dry_run=False)


def run(**over):
    return check_settings(Settings(_env_file=None, **{**GOOD, **over}))


def fails(results):
    return {name for level, name, _ in results if level == "FAIL"}


@pytest.fixture()
def legal_approved(monkeypatch):
    monkeypatch.setitem(merchant_form.LEGAL_REVIEW, "status", "approved")


def test_a_correct_deployment_has_no_blockers_once_the_wording_is_approved(legal_approved):
    assert fails(run()) == set()


def test_the_draft_attestation_text_is_always_a_blocker():
    assert merchant_form.LEGAL_REVIEW["status"] != "approved", "this repository must ship with the wording marked as NOT approved"
    assert "legal_review" in fails(run())


@pytest.mark.parametrize("over, blocker", [
    ({"allow_test_evidence": True}, "test_evidence"),
    ({"ops_api_key": ""}, "ops_key"),
    ({"ops_api_key": "dev-ops-key"}, "ops_key"),
    ({"ops_api_key": "short"}, "ops_key"),
    ({"id_hash_secret": "dev-only-change-me"}, "id_hash_secret"),
    ({"frontend_url": "http://localhost:3000"}, "frontend_url"),
    ({"frontend_url": "http://joeat.example.org"}, "frontend_url"),                      # not https
    ({"cors_origins": "http://localhost:3000"}, "cors"),                                # page would load, every API call would be blocked
])
def test_each_unsafe_setting_is_a_blocker(legal_approved, over, blocker):
    assert blocker in fails(run(**over))


def test_dev_auth_and_dry_run_are_warnings_not_blockers(legal_approved):
    r = run(auth_mode="dev", line_dry_run=True)
    assert fails(r) == set() and {n for lv, n, _ in r if lv == "WARN"} == {"auth_mode", "line_dry_run"}
