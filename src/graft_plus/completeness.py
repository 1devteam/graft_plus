"""Integrity of the reconstructed map. Acknowledgements do not repair."""

from __future__ import annotations

from typing import Any


def audit(graph: dict[str, Any], overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    overlay = overlay or {}
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
    acknowledged = {str(x) for x in (overlay.get("acknowledged_findings") or [])}
    findings = []
    for item in overlay.get("findings") or []:
        fid = str(item.get("id") or "")
        blocking = bool(item.get("blocking"))
        if blocking and fid and fid not in acknowledged:
            findings.append(fid)
    return {
        "schema_version": "1.0",
        "integrity_pass": not missing,
        "undefined_edge_endpoints": missing,
        "static_cycle_count": len(cycles),
        "node_count": graph.get("metrics", {}).get("node_count", len(graph.get("nodes", []))),
        "edge_count": graph.get("metrics", {}).get("edge_count", len(graph.get("edges", []))),
        "unacknowledged_blocking_findings": findings,
        "acknowledged_findings": sorted(acknowledged),
        "note": "An acknowledgement means the detector already knows the finding. It is not a repair.",
    }
