import argparse
import shutil
from pathlib import Path

PRUNE_LIST = [
    # Legacy monolith package, now superseded by core/* and exchange/*
    "bot",
    # Duplicate or superseded exchange abstractions (kept PaperBroker under exchange/paper.py)
    "exchange/paper_legacy.py",
    # Old runners (left shims in place, these are extra if present)
    "runner",
    # Outdated ops wrappers if duplicated under api/routes
    "ops/notifier.py",
    "ops/__init__.py",
    # Stray risk experiments moved under core/risk or removed
    "risk/taxonomy.py",
    "risk/state.py",
    # One-off scripts replaced by tests or unified tools
    "backtest_strategy.py",
    # Old strategy duplicates if still present
    "strategy.py",
    "strategies_old",
    # Generated or sample datasets that should not live in repo
    "data/exports/decisions.csv",
    "data/exports/trades.csv",
    "exports/decisions.csv",
    "exports/trades.csv",
]


def safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def remove_path(p: Path):
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()


def main():
    parser = argparse.ArgumentParser(description="Prune legacy files and folders safely.")
    parser.add_argument("--apply", action="store_true", help="Actually delete files")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    print(f"Project root: {root}")

    to_remove: list[Path] = []
    for rel in PRUNE_LIST:
        p = (root / rel).resolve()
        if safe_exists(p):
            to_remove.append(p)

    if not to_remove:
        print("Nothing to remove. Repo already clean.")
        return

    print("Planned removals:")
    for p in to_remove:
        print(f"  - {p.relative_to(root)}")

    if args.dry_run and not args.apply:
        print("Dry-run complete. No changes made.")
        return

    if not args.apply:
        print("Pass --apply to perform deletion, or use --dry-run to preview.")
        return

    for p in to_remove:
        try:
            remove_path(p)
            print(f"Removed: {p.relative_to(root)}")
        except Exception as e:
            print(f"Failed to remove {p}: {e}")


if __name__ == "__main__":
    main()
