"""Generate a lightweight JSON index of the repository useful for LLM ingestion.

Writes repo_index.json with: path, size, first_line, docstring (if Python), and sha1 (optional).
"""

from pathlib import Path
import json
import hashlib
import ast

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "repo_index.json"

IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    try:
        with p.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def extract_docstring(p: Path) -> str | None:
    if p.suffix != ".py":
        return None
    try:
        src = p.read_text(encoding="utf-8")
        mod = ast.parse(src)
        doc = ast.get_docstring(mod)
        return doc
    except Exception:
        return None


def summarize_file(p: Path) -> dict:
    try:
        size = p.stat().st_size
    except Exception:
        size = 0
    try:
        first = p.read_text(encoding="utf-8").splitlines()[0] if size else ""
    except Exception:
        first = ""
    return {
        "path": str(p.relative_to(ROOT)),
        "size": size,
        "first_line": first,
        "docstring": extract_docstring(p),
        "sha1": file_sha1(p),
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
        if p.suffix in {".png", ".jpg", ".jpeg", ".gif", ".pyc", ".db"}:
            continue
        out.append(summarize_file(p))
    return out


if __name__ == "__main__":
    idx = walk_repo(ROOT)
    OUT.write_text(json.dumps({"files": idx}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
