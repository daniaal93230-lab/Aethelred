from __future__ import annotations

from fastapi import Request
from typing import cast

from risk.engine import RiskEngine


def get_risk_engine(request: Request) -> RiskEngine:
    # app.state attributes are untyped at runtime; cast to remove mypy Any->RiskEngine warning
    return cast(RiskEngine, getattr(request.app.state, "risk_engine", None))
