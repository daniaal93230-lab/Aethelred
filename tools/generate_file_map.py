#!/usr/bin/env python3
"""Generate file_map.json and file_map.yaml for the repository.

Usage:
    python tools/generate_file_map.py

Writes `file_map.json` and `file_map.yaml` (if PyYAML installed) at the repo root.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "file_map.json"
OUT_YAML = ROOT / "file_map.yaml"


def should_skip(path: Path) -> bool:
    # Skip virtual envs, caches, git internals, and pyc files
    parts = {p.lower() for p in path.parts}
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", ".pytest_cache"}
    if parts & skip_dirs:
        return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    return False


def scan() -> dict:
    files = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir():
            continue
        if should_skip(p):
            continue

        try:
            stat = p.stat()
        except Exception:
            continue

        rel = p.relative_to(ROOT).as_posix()
        entry = {
            "path": rel,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "iso_mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            "file_uri": f"file:///{p.as_posix()}",
        }
        files.append(entry)

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "root": str(ROOT),
        "files": files,
        "file_count": len(files),
    }
    return manifest


def write_json(manifest: dict) -> None:
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def write_yaml(manifest: dict) -> None:
    try:
        import yaml
    except Exception:
        print("PyYAML not installed; skipping YAML output")
        return
    with OUT_YAML.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f)


def main() -> int:
    print(f"Scanning repository root: {ROOT}")
    manifest = scan()
    print(f"Found {manifest['file_count']} files")
    write_json(manifest)
    write_yaml(manifest)
    print(f"Wrote {OUT_JSON}")
    if OUT_YAML.exists():
        print(f"Wrote {OUT_YAML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
