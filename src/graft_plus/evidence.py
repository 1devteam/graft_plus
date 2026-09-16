"""Normalize compact source anchors for every generated graph fact."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _line_count(path: Path) -> int:
    try:
        return max(1, len(path.read_text(encoding="utf-8").splitlines()))
    except (OSError, UnicodeDecodeError):
        return 1


def attach_evidence_anchors(subject: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    """Attach line/symbol evidence without changing legacy evidence paths."""
    line_counts: dict[str, int] = {}

    def count(source: str) -> int:
        if source not in line_counts:
            line_counts[source] = _line_count(subject / source)
        return line_counts[source]

    node_by_id = {str(node["id"]): node for node in nodes}
    for node in nodes:
        source = node.get("source")
        if not isinstance(source, str) or not source or not (subject / source).is_file():
            continue
        precise = bool(node.get("start_line") or node.get("line"))
        start = int(node.get("start_line") or node.get("line") or 1)
        end = int(node.get("end_line") or (start if precise else count(source)))
        node["evidence_anchor"] = {
            "source": source,
            "start_line": start,
            "end_line": max(start, end),
            "symbol": node.get("name") or node.get("handler") or node.get("label"),
            "detector": node.get("detector") or "source_inventory",
            "precision": "line" if precise else "file",
        }
    for edge in edges:
        source = edge.get("evidence")
        if not isinstance(source, str) or not source or not (subject / source).is_file():
            continue
        target = node_by_id.get(str(edge.get("to"))) or {}
        start = edge.get("start_line")
        end = edge.get("end_line")
        if start is None and target.get("source") == source:
            start = target.get("start_line") or target.get("line")
            end = target.get("end_line") or start
        precise = start is not None
        start_value = int(start or 1)
        edge["evidence_anchor"] = {
            "source": source,
            "start_line": start_value,
            "end_line": max(start_value, int(end or (start_value if precise else count(source)))),
            "symbol": edge.get("symbol") or target.get("name") or target.get("handler") or target.get("label"),
            "detector": edge.get("detector") or ("target_declaration" if precise else "source_relationship"),
            "precision": "line" if precise else "file",
        }
