"""Compose the decipher pack. Never grants merge or execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from graft_plus import GRANTS_EXECUTION_AUTHORITY, IMPLEMENTS_PLAN, MERGE_AUTHORIZATION, PACKAGE, PRODUCT


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decide(*, graph: dict[str, Any], impact: dict[str, Any], completeness: dict[str, Any]) -> dict[str, Any]:
    blocking = list(completeness.get("unacknowledged_blocking_findings") or [])
    if not completeness.get("integrity_pass") or blocking:
        disposition = "blocked"
    elif impact.get("unmapped_changed_file_count"):
        disposition = "review-required"
    else:
        disposition = "clear"
    return {
        "schema_version": "1.0",
        "product": PRODUCT,
        "package": PACKAGE,
        "role": "fact-substrate",
        "decision": {
            "architecture_disposition": disposition,
            "merge_authorization": MERGE_AUTHORIZATION,
            "full_ci_required": True,
            "blocking_reasons": blocking + (["undefined_edge_endpoints"] if not completeness.get("integrity_pass") else []),
            "review_reasons": ["unmapped_changed_files"] if impact.get("unmapped_changed_file_count") else [],
            "warnings": [],
        },
        "grants_execution_authority": GRANTS_EXECUTION_AUTHORITY,
        "implementsPlan": IMPLEMENTS_PLAN,
        "completeness": {
            "integrity_pass": completeness.get("integrity_pass"),
            "undefined_edge_endpoints": completeness.get("undefined_edge_endpoints") or [],
            "unacknowledged_blocking_findings": blocking,
        },
        "impact": {
            "changed_files": impact.get("changed_files") or [],
            "changed_node_ids": [n["id"] for n in impact.get("changed_nodes") or []],
            "unmapped_changed_files": impact.get("unmapped_changed_files") or [],
            "impacted_tests": impact.get("impacted_tests") or [],
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
        ],
    }
