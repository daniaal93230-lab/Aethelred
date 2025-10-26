# Aethelred

Trading research and paper-trading stack with simple FastAPI endpoints, risk controls, and lightweight ML.

## Cleanup and structure

We are consolidating to a single execution path and removing legacy, duplicate, or superseded modules.
Run the prune script once after this patch:

```bash
python scripts/prune_legacy.py --apply
```

If you want a dry run first:

```bash
python scripts/prune_legacy.py --dry-run
```

After pruning, use the unified runner:

```bash
python run.py --mode paper   # or --mode live
```

LLM-friendly quickstart
----------------------
This repo includes small helpers to make analysis easier for tools and LLMs:

- `REPO_OVERVIEW.md` — short map of important files and entrypoints.
- `scripts/generate_repo_index.py` — produces `repo_index.json` (machine-readable file list + docstrings).
- `scripts/list_routes.py` — prints registered FastAPI routes (useful to build an API contract quickly).

To generate a compact machine-friendly index of the repo:

```powershell
python scripts/generate_repo_index.py
```

Then open `repo_index.json` to see files, docstrings and first lines.
