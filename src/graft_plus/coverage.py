"""Unmapped source files and stale graph sources.

Unmapped: source on disk with no graph node.
Stale: graph node whose source file is gone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graft_plus.inventory import relevant_files, rel


def inventory(subject: Path, graph: dict[str, Any]) -> dict[str, Any]:
    mapped = {
        str(node["source"]).replace("\\", "/")
        for node in graph.get("nodes") or []
        if isinstance(node.get("source"), str) and node.get("source")
    }
    unmapped: list[str] = []
    for path in relevant_files(subject):
        source = rel(subject, path)
        if source in mapped:
            continue
        unmapped.append(source)
    stale: list[dict[str, str]] = []
    if subject is not None:
        for node in graph.get("nodes") or []:
            source = node.get("source")
            if not isinstance(source, str) or not source:
                continue
            if not (subject / source).exists():
                stale.append({"id": str(node.get("id")), "source": source})
    facts = graph.get("facts") or {}
    return {
        "unmapped_source_files": sorted(unmapped),
        "stale_graph_sources": sorted(stale, key=lambda item: item["id"]),
        "unmapped_source_file_count": len(unmapped),
        "stale_graph_source_count": len(stale),
        "relationship_unparsed_files": list(facts.get("relationship_unparsed_files") or []),
        "relationship_unparsed_file_count": int(facts.get("relationship_unparsed_file_count") or 0),
        "note": "Every relevant file should be inventoried. Relationship-unparsed files are visible but have no language relationship adapter.",
    }
