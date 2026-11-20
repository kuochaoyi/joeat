"""Tiny check that the ORM models map onto the migrated schema. Run from backend/: python scripts/smoke_models.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.db.session import new_session  # noqa: E402
from app.models.identity import Restaurant  # noqa: E402
from app.models.ref import Attribute, ConstraintDecisionRule  # noqa: E402

db = new_session()
print("restaurants", db.scalar(select(func.count()).select_from(Restaurant)))
print("attributes", db.scalar(select(func.count()).select_from(Attribute)))
print("rules", db.scalar(select(func.count()).select_from(ConstraintDecisionRule)))
print([(r.canonical_name, r.pool_status) for r in db.scalars(select(Restaurant).limit(2))])
