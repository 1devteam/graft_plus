"""Compose the decipher pack. Never grants merge or execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from graft_plus import GRANTS_EXECUTION_AUTHORITY, IMPLEMENTS_PLAN, MERGE_AUTHORIZATION, PACKAGE, PRODUCT


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ids(items: list[Any]) -> list[str]:
    out = []
    for item in items or []:
        if isinstance(item, str) and item:
            out.append(item)
        elif isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]))
    return sorted(set(out))


def decide(*, graph: dict[str, Any], impact: dict[str, Any], completeness: dict[str, Any]) -> dict[str, Any]:
    blocking = list((completeness.get("integrity") or {}).get("unacknowledged_blocking_findings") or completeness.get("unacknowledged_blocking_findings") or [])
    residuals = completeness.get("residuals") or {}
    review = []
    if impact.get("unmapped_changed_file_count"):
        review.append("unmapped_changed_files")
    if residuals.get("unmapped_source_files"):
        review.append("unmapped_source_files")
    if residuals.get("relationship_unparsed_files"):
        review.append("partial_relationship_coverage")
    if residuals.get("unresolved_relationship_boundary_count"):
        review.append("runtime_or_build_context_required")
    if residuals.get("stale_graph_sources"):
        review.append("stale_graph_sources")
    if (completeness.get("integrity") or {}).get("known_violations"):
        review.append("known_violations_visible")
    warnings = []
    if residuals.get("no_git_range"):
        warnings.append("no_git_range")
    if residuals.get("unresolved_package_roots"):
        warnings.append("unresolved_imports")
    integrity_pass = bool(completeness.get("integrity_pass") if "integrity_pass" in completeness else (completeness.get("integrity") or {}).get("pass"))
    if not integrity_pass or blocking:
        disposition = "blocked"
    elif impact.get("unmapped_changed_file_count"):
        disposition = "review-required"
    else:
        disposition = "clear"
    return {
        "schema_version": "1.1",
        "product": PRODUCT,
        "package": PACKAGE,
        "role": "fact-substrate",
        "decision": {
            "architecture_disposition": disposition,
            "merge_authorization": MERGE_AUTHORIZATION,
            "full_ci_required": True,
            "blocking_reasons": blocking + (["undefined_edge_endpoints"] if not completeness.get("integrity_pass") else []),
            "review_reasons": review,
            "warnings": warnings,
        },
        "grants_execution_authority": GRANTS_EXECUTION_AUTHORITY,
        "implementsPlan": IMPLEMENTS_PLAN,
        "completeness": {
            "integrity_pass": completeness.get("integrity_pass"),
            "undefined_edge_endpoints": completeness.get("undefined_edge_endpoints") or [],
            "unacknowledged_blocking_findings": blocking,
            "acknowledged_semantic_findings": completeness.get("acknowledged_findings") or [],
            "missing_semantic_edge_evidence": (completeness.get("integrity") or {}).get("missing_semantic_edge_evidence") or [],
            "semantic_reconciliation_counts": completeness.get("semantic_reconciliation_counts") or {},
            "unmapped_source_files": residuals.get("unmapped_source_files") or [],
            "stale_graph_sources": residuals.get("stale_graph_sources") or [],
            "relationship_unparsed_files": residuals.get("relationship_unparsed_files") or [],
            "relationship_boundary_count": residuals.get("relationship_boundary_count") or 0,
            "unresolved_relationship_boundary_count": residuals.get("unresolved_relationship_boundary_count") or 0,
            "relationship_boundary_counts_by_kind": residuals.get("relationship_boundary_counts_by_kind") or {},
        },
        "residuals": residuals,
        "impact": {
            "changed_files": impact.get("changed_files") or [],
            "changed_node_ids": _ids(impact.get("changed_nodes") or []),
            "unmapped_changed_files": impact.get("unmapped_changed_files") or [],
            "upstream_consumers": _ids(impact.get("upstream_consumers") or []),
            "downstream_dependencies": _ids(impact.get("downstream_dependencies") or []),
            "affected_semantic_node_ids": _ids(impact.get("affected_semantic_nodes") or []),
            "dependency_semantic_node_ids": _ids(impact.get("dependency_semantic_nodes") or []),
            "impacted_tests": impact.get("impacted_tests") or [],
            "relevant_invariant_ids": _ids(impact.get("relevant_invariants") or []),
        },
        "inputs": {
            "canonical_graph_sha256": _sha(graph),
            "metrics": graph.get("metrics") or {},
        },
        "negatives": [
            "This pack is a map. It is not a plan.",
            "merge_authorization is not-determined even when disposition is clear.",
            "An acknowledgement is not a repair.",
            "Do not invent missing nodes.",
            "Unresolved imports are facts, not missing files.",
            "Overlay stays residual until a reviewed relationship is attached.",
        ],
    }
