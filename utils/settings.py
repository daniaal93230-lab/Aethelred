import os


def qa_mode() -> bool:
    """
    Enable QA-only endpoints when QA_MODE=1 or APP_ENV=qa.
    Defaults to False in production.
    """
    v = os.getenv("QA_MODE", "0")
    return v in ("1", "true", "True") or os.getenv("APP_ENV") == "qa"
