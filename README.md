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
