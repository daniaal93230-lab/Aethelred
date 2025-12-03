"""Insight Engine package (Phase 6.E)

This package provides offline/async analytics (MAE/MFE) and is not
automatically attached to the live engine. It is intentionally lightweight
and pure-Python so it won't affect test startup.
"""

__all__ = ["InsightEngine", "compute_mae_mfe"]
