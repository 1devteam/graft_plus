"""Integrity of the reconstructed map. Acknowledgements do not repair."""

from __future__ import annotations

from typing import Any


def audit(graph: dict[str, Any], overlay: dict[str, Any] | None = None, impact: dict[str, Any] | None = None) -> dict[str, Any]:
    overlay = overlay or {}
    impact = impact or {}
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
    unresolved = list((graph.get("facts") or {}).get("unresolved_imports") or [])
    overlay_nodes = [n for n in graph["nodes"] if n.get("layer") == "overlay"]
    residuals = {
        "overlay": "attached" if overlay_nodes else "residual",
        "unresolved_imports": unresolved,
        "unresolved_package_roots": list((graph.get("facts") or {}).get("unresolved_package_roots") or []),
        "no_git_range": not bool(impact.get("changed_files")),
        "unmapped_changed_files": list(impact.get("unmapped_changed_files") or []),
        "note": "Residuals stay visible. Unresolved imports are facts, not missing files. Overlay stays residual until a reviewed relationship is attached.",
    }
    return {
        "schema_version": "1.1",
        "integrity_pass": not missing,
        "undefined_edge_endpoints": missing,
        "static_cycle_count": len(cycles),
        "node_count": graph.get("metrics", {}).get("node_count", len(graph.get("nodes", []))),
        "edge_count": graph.get("metrics", {}).get("edge_count", len(graph.get("edges", []))),
        "unacknowledged_blocking_findings": findings,
        "acknowledged_findings": sorted(acknowledged),
        "residuals": residuals,
        "note": "An acknowledgement means the detector already knows the finding. It is not a repair.",
    }
