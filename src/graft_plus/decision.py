"""Project reconstruction evidence into independent assurance propositions."""

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
    integrity = completeness.get("integrity") or {}
    residuals = completeness.get("residuals") or {}
    blocking = list(integrity.get("unacknowledged_blocking_findings") or completeness.get("unacknowledged_blocking_findings") or [])
    collisions = int(completeness.get("identity_collision_count") or integrity.get("identity_collision_count") or 0)
    identity_pass = bool(completeness.get("identity_integrity_pass", integrity.get("identity_integrity_pass", not collisions)))
    artifact_pass = bool(completeness.get("integrity_pass") if "integrity_pass" in completeness else integrity.get("pass"))

    structural_gaps = []
    for key, reason in (("unmapped_source_file_count", "unmapped_source_files"), ("relationship_unparsed_file_count", "relationship_unparsed_files"), ("unresolved_relationship_boundary_count", "runtime_or_build_context_required"), ("unresolved_import_count", "unresolved_references"), ("stale_graph_source_count", "stale_graph_sources")):
        if residuals.get(key):
            structural_gaps.append(reason)

    changed_files = list(impact.get("changed_files") or [])
    unmapped_changed = list(impact.get("unmapped_changed_files") or [])
    known_violations = list(integrity.get("known_violations") or [])

    dimensions = {
        "artifact_integrity": "passed" if artifact_pass else "blocked",
        "identity_integrity": "passed" if identity_pass else "blocked",
        "structural_coverage": "gaps-visible" if structural_gaps else "no-known-gaps",
        "architectural_reconstruction": "bounded" if not structural_gaps and artifact_pass else "incomplete",
        "change_evidence": "not-requested" if not changed_files else ("partial" if unmapped_changed else "available"),
        "proof_readiness": "not-established",
        "execution_authority": "not-granted",
        "merge_authority": MERGE_AUTHORIZATION,
    }

    review = list(structural_gaps)
    if unmapped_changed:
        review.append("unmapped_changed_files")
    if known_violations:
        review.append("known_violations_visible")
    if not changed_files:
        review.append("no_git_range")
    review = sorted(set(review))

    if not artifact_pass or not identity_pass or blocking:
        disposition = "blocked"
    elif review:
        disposition = "review-required"
    else:
        disposition = "clear"

    blocking_reasons = list(blocking)
    if not identity_pass:
        blocking_reasons.append("canonical_identity_collision")
    if completeness.get("undefined_edge_endpoints"):
        blocking_reasons.append("undefined_edge_endpoints")
    if integrity.get("missing_semantic_edge_evidence"):
        blocking_reasons.append("missing_semantic_edge_evidence")

    return {
        "schema_version": "1.3",
        "product": PRODUCT,
        "package": PACKAGE,
        "role": "fact-substrate",
        "decision": {
            "architecture_disposition": disposition,
            "dimensions": dimensions,
            "merge_authorization": MERGE_AUTHORIZATION,
            "full_ci_required": True,
            "blocking_reasons": sorted(set(blocking_reasons)),
            "review_reasons": review,
            "warnings": ["unresolved_references_classified"] if residuals.get("unresolved_import_classes") else [],
        },
        "grants_execution_authority": GRANTS_EXECUTION_AUTHORITY,
        "implementsPlan": IMPLEMENTS_PLAN,
        "completeness": {
            "integrity_pass": completeness.get("integrity_pass"),
            "identity_integrity_pass": identity_pass,
            "identity_collision_count": collisions,
            "duplicate_node_ids": completeness.get("duplicate_node_ids") or integrity.get("duplicate_node_ids") or [],
            "undefined_edge_endpoints": completeness.get("undefined_edge_endpoints") or [],
            "unacknowledged_blocking_findings": blocking,
            "acknowledged_semantic_findings": completeness.get("acknowledged_findings") or [],
            "missing_semantic_edge_evidence": integrity.get("missing_semantic_edge_evidence") or [],
            "semantic_reconciliation_counts": completeness.get("semantic_reconciliation_counts") or {},
            "unmapped_source_files": residuals.get("unmapped_source_files") or [],
            "stale_graph_sources": residuals.get("stale_graph_sources") or [],
            "relationship_unparsed_files": residuals.get("relationship_unparsed_files") or [],
            "relationship_boundary_count": residuals.get("relationship_boundary_count") or 0,
            "unresolved_relationship_boundary_count": residuals.get("unresolved_relationship_boundary_count") or 0,
            "relationship_boundary_counts_by_kind": residuals.get("relationship_boundary_counts_by_kind") or {},
            "unresolved_import_count": residuals.get("unresolved_import_count") or 0,
            "unresolved_import_classes": residuals.get("unresolved_import_classes") or {},
            "evidence_precision_counts": residuals.get("evidence_precision_counts") or {},
            "contract_source_count": residuals.get("contract_source_count") or 0,
            "contract_declaration_count": residuals.get("contract_declaration_count") or 0,
            "contract_declaration_counts_by_kind": residuals.get("contract_declaration_counts_by_kind") or {},
            "configuration_key_count": residuals.get("configuration_key_count") or 0,
            "deployment_fact_count": residuals.get("deployment_fact_count") or 0,
            "deployment_fact_counts_by_kind": residuals.get("deployment_fact_counts_by_kind") or {},
            "subsystem_count": residuals.get("subsystem_count") or 0,
            "subsystem_direct_member_counts": residuals.get("subsystem_direct_member_counts") or {},
            "cross_language_subsystem_count": residuals.get("cross_language_subsystem_count") or 0,
            "cross_language_subsystems": residuals.get("cross_language_subsystems") or [],
            "build_definition_count": residuals.get("build_definition_count") or 0,
            "build_definition_counts_by_system": residuals.get("build_definition_counts_by_system") or {},
            "build_input_edge_count": residuals.get("build_input_edge_count") or 0,
            "governance_boundary_count": residuals.get("governance_boundary_count") or 0,
            "governance_boundary_counts_by_kind": residuals.get("governance_boundary_counts_by_kind") or {},
            "source_provenance_counts": residuals.get("source_provenance_counts") or {},
        },
        "residuals": residuals,
        "impact": {
            "changed_files": changed_files,
            "changed_node_ids": _ids(impact.get("changed_nodes") or []),
            "unmapped_changed_files": unmapped_changed,
            "upstream_consumers": _ids(impact.get("upstream_consumers") or []),
            "downstream_dependencies": _ids(impact.get("downstream_dependencies") or []),
            "affected_semantic_node_ids": _ids(impact.get("affected_semantic_nodes") or []),
            "dependency_semantic_node_ids": _ids(impact.get("dependency_semantic_nodes") or []),
            "impacted_tests": impact.get("impacted_tests") or [],
            "relevant_invariant_ids": _ids(impact.get("relevant_invariants") or []),
        },
        "inputs": {"canonical_graph_sha256": _sha(graph), "metrics": graph.get("metrics") or {}},
        "negatives": [
            "This pack is a map. It is not a plan.",
            "No single disposition substitutes for the independent assurance dimensions.",
            "merge_authorization is not-determined even when disposition is clear.",
            "An acknowledgement is not a repair.",
            "Do not invent missing nodes or unresolved targets.",
            "Unresolved references are classified residual evidence, not proof of missing files.",
            "Overlay stays residual until a reviewed relationship is attached.",
        ],
    }
