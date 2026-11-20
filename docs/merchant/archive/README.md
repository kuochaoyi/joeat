# Archive: first draft of the merchant self-declaration schema

These files are **historical**. They record how the design was first validated (52 checks on PostgreSQL 16.2).

- `draft_0003_merchant_declaration.sql` – the first draft. **Superseded** by `backend/app/db/sql/0003_merchant_declaration.sql` (Alembic revision 0003).
- `validation_results.txt` – the result of running the draft's 52 checks.
- `validate_draft.py` – **no longer runs**: the seed files now assume migration 0003, which this script predates. Do not rely on it.

What replaced it: migration 0003 + `backend/tests/integration/test_merchant_ops.py` and `test_migrations.py`, which cover the same scenarios (and the decisions made afterwards) through the real reviewer API.

Differences between the draft and the final version are listed in `docs/decisions/0001-merchant-declaration.md`.
