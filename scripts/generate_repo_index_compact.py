"""Generate a compact JSON index of the repository suitable for committing.

This writes `repo_index_compact.json` with limited fields to keep size small.
- skips large files (>100KB)
- only includes path, size, first_line, docstring (truncated to 512 chars)

Intended for CI to regenerate for LLM ingestion without bloating the repo.
"""

from pathlib import Path
import json
import ast

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "repo_index_compact.json"
MAX_FILE_BYTES = 100 * 1024  # 100 KB
MAX_DOCSTRING_CHARS = 512
IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "ml_models", "data"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".pyc", ".db", ".sqlite", ".pt", ".pth", ".pkl"}


def extract_docstring(p: Path) -> str | None:
    if p.suffix != ".py":
        return None
    try:
        src = p.read_text(encoding="utf-8")
        mod = ast.parse(src)
        doc = ast.get_docstring(mod)
        if not doc:
            return None
        doc = doc.strip().replace("\n\n", " \n ")
        if len(doc) > MAX_DOCSTRING_CHARS:
            return doc[:MAX_DOCSTRING_CHARS] + "..."
        return doc
    except Exception:
        return None


def summarize_file(p: Path) -> dict | None:
    try:
        size = p.stat().st_size
    except Exception:
        return None
    if size > MAX_FILE_BYTES:
        return None
    try:
        first = p.read_text(encoding="utf-8").splitlines()[0] if size else ""
    except Exception:
        first = ""
    doc = extract_docstring(p)
    return {
        "path": str(p.relative_to(ROOT)).replace("\\", "/"),
        "size": size,
        "first_line": first[:200],
        "docstring": doc,
    }


def walk_repo(root: Path) -> list:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            if p.name in IGNORE_DIRS:
                continue
            else:
                continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        if p.suffix in SKIP_SUFFIX:
            continue
        rec = summarize_file(p)
        if rec is not None:
            out.append(rec)
    return out


if __name__ == "__main__":
    idx = walk_repo(ROOT)
    OUT.write_text(json.dumps({"files": idx}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {len(idx)} entries")
