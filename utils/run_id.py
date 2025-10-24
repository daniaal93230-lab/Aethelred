from datetime import datetime


def current_run_id() -> str:
    """Return a compact UTC run identifier, minute granularity."""
    return datetime.utcnow().strftime("RUN_%Y%m%d_%H%M")
