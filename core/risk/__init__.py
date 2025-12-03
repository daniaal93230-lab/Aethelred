"""Risk package unifying legacy risk functions and RiskEngineV3.

This package intentionally coexists with the legacy module at
`core/risk.py`. A package named `core.risk` will shadow the module
file, so we import the legacy file explicitly by filesystem path and
re-export its public API so existing imports keep working.
"""

from __future__ import annotations

import os
import importlib.util
from typing import Any

# ------------------------------------------------------------------
# Explicitly import the legacy module file `core/risk.py` by path to
# bypass package shadowing and load the original definitions.
# ------------------------------------------------------------------

# Default fallbacks
RiskConfig = None  # type: Any
compute_atr = None  # type: Any
position_size_usd = None  # type: Any

try:
	# core/risk/__init__.py -> _here is core/risk/
	_here = os.path.dirname(__file__)
	_core_dir = os.path.dirname(_here)
	_legacy_path = os.path.join(_core_dir, "risk.py")

	if os.path.isfile(_legacy_path):
		spec = importlib.util.spec_from_file_location("core.risk_legacy", _legacy_path)
		legacy_mod = importlib.util.module_from_spec(spec)
		# type: ignore - loader exists when spec is valid
		spec.loader.exec_module(legacy_mod)  # type: ignore

		RiskConfig = getattr(legacy_mod, "RiskConfig", None)
		compute_atr = getattr(legacy_mod, "compute_atr", None)
		position_size_usd = getattr(legacy_mod, "position_size_usd", None)
	else:
		# legacy file not found; keep fallbacks as None
		pass
except Exception:
	# Fail-safe: keep None values if import fails
	RiskConfig = None  # type: Any
	compute_atr = None  # type: Any
	position_size_usd = None  # type: Any

# Export the new engine scaffold alongside the legacy API
from .engine_v3 import RiskEngineV3

__all__ = [
	"RiskEngineV3",
	"RiskConfig",
	"compute_atr",
	"position_size_usd",
]
