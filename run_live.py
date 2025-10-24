"""
Deprecated: use run.py
Kept temporarily to avoid breaking shortcuts.
This shim forwards to the unified runner.
Will be removed after the next release.
"""
from run import main

if __name__ == "__main__":
    main(mode="live")
