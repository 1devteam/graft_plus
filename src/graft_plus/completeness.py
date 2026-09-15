"""Integrity of the reconstructed map."""

from __future__ import annotations

from typing import Any


def audit(graph: dict[str, Any]) -> dict[str, Any]:
    known = {str(n["id"]) for n in graph["nodes"]}
    missing = sorted(
        {
            str(end)
            for edge in graph["edges"]
            for end in (edge.get("from"), edge.get("to"))
            if end not in known
        }
    )
    cycles = graph.get("metrics", {}).get("static_cycles") or []
    return {
        "schema_version": "1.0",
        "integrity_pass": not missing,
        "undefined_edge_endpoints": missing,
        "static_cycle_count": len(cycles),
        "node_count": graph.get("metrics", {}).get("node_count", len(graph.get("nodes", []))),
        "edge_count": graph.get("metrics", {}).get("edge_count", len(graph.get("edges", []))),
        "unacknowledged_blocking_findings": [],
    }
