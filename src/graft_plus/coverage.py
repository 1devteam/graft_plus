"""Unmapped source files and stale graph sources.

Unmapped: source on disk with no graph node.
Stale: graph node whose source file is gone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SKIP = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache"}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".php"}


def _rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def inventory(subject: Path, graph: dict[str, Any]) -> dict[str, Any]:
    mapped = {
        str(node["source"]).replace("\\", "/")
        for node in graph.get("nodes") or []
        if isinstance(node.get("source"), str) and node.get("source")
    }
    unmapped: list[str] = []
    for path in subject.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        rel = _rel(subject, path)
        if rel in mapped:
            continue
        unmapped.append(rel)
    stale: list[dict[str, str]] = []
    if subject is not None:
        for node in graph.get("nodes") or []:
            source = node.get("source")
            if not isinstance(source, str) or not source:
                continue
            if not (subject / source).exists():
                stale.append({"id": str(node.get("id")), "source": source})
    return {
        "unmapped_source_files": sorted(unmapped),
        "stale_graph_sources": sorted(stale, key=lambda item: item["id"]),
        "unmapped_source_file_count": len(unmapped),
        "stale_graph_source_count": len(stale),
        "note": "Unmapped files exist on disk and are not graph nodes. Stale sources are graph nodes whose files are gone.",
    }
