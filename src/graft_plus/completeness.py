"""Completeness audit with ratchet. Ported from ajenda-ai graph_completeness_audit.py.

An acknowledgement means the detector already knows the finding.
It is not a repair. New unacknowledged blocking findings fail closed.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from graft_plus.coverage import inventory as coverage_inventory
from graft_plus.residuals import classify_unresolved_reference

TEST_EDGE_TYPES = frozenset({"tests", "tests_function"})
STATIC_EDGE_TYPE = "imports"


def _collect_findings(graph: dict[str, Any], overlay: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [dict(item) for item in (graph.get("semantic_findings") or [])]
    seen = {str(item.get("id")) for item in findings if item.get("id")}
    acknowledged = {str(x) for x in (overlay.get("acknowledged_findings") or [])}
    for item in overlay.get("findings") or []:
        fid = str(item.get("id") or "")
        if not fid or fid in seen:
            continue
        row = dict(item)
        row["id"] = fid
        findings.append(row)
        seen.add(fid)
    for item in findings:
        fid = str(item.get("id") or "")
        item["acknowledged"] = bool(item.get("acknowledged")) or fid in acknowledged
    return findings


def _classify_unresolved_imports(graph: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in (graph.get("facts") or {}).get("unresolved_imports") or []:
        counts[
            classify_unresolved_reference(
                str(row.get("specifier") or ""),
                str(row.get("from") or ""),
            )
        ] += 1
    return dict(sorted(counts.items()))


def audit(graph: dict[str, Any], overlay: dict[str, Any] | None = None, subject: Path | None = None) -> dict[str, Any]:
    """Validate the instrument output and expose unresolved factual residuals."""

    overlay = overlay or {}
    node_id_counts = Counter(str(node.get("id") or "") for node in graph.get("nodes") or [] if node.get("id"))
    duplicate_node_ids = sorted(node_id for node_id, count in node_id_counts.items() if count > 1)
    duplicate_node_occurrences = sum(count - 1 for count in node_id_counts.values() if count > 1)
    known = {str(n["id"]) for n in graph["nodes"]}
    missing_endpoints = sorted(
        {
            str(end)
            for edge in graph["edges"]
            for end in (edge.get("from"), edge.get("to"))
            if end not in known
        }
    )
    findings = _collect_findings(graph, overlay)
    unacknowledged_blocking = sorted(
        str(item["id"]) for item in findings if bool(item.get("blocking")) and not bool(item.get("acknowledged")) and item.get("id")
    )
    acknowledged = sorted(str(item["id"]) for item in findings if bool(item.get("acknowledged")) and item.get("id"))
    known_violations = sorted(str(item["id"]) for item in findings if str(item.get("classification") or "") == "known_violation")
    missing_edge_evidence = []
    if subject is not None:
        for edge in graph.get("edges") or []:
            if str(edge.get("type")) in {STATIC_EDGE_TYPE, *TEST_EDGE_TYPES}:
                continue
            evidence = edge.get("evidence")
            if not isinstance(evidence, str) or not evidence:
                missing_edge_evidence.append(f"{edge.get('from')}->{edge.get('to')}:{edge.get('type')}")
            elif not (subject / evidence).exists():
                missing_edge_evidence.append(evidence)
    integrity_pass = not duplicate_node_ids and not missing_endpoints and not unacknowledged_blocking and not missing_edge_evidence
    overlay_nodes = [n for n in graph["nodes"] if n.get("layer") == "overlay"]
    unresolved_roots = list((graph.get("facts") or {}).get("unresolved_package_roots") or [])
    coverage = coverage_inventory(subject, graph) if subject is not None else {
        "unmapped_source_files": [],
        "stale_graph_sources": [],
        "unmapped_source_file_count": 0,
        "stale_graph_source_count": 0,
    }
    residuals = {
        "overlay": "attached" if overlay_nodes else "residual",
        "identity_collision_count": duplicate_node_occurrences,
        "duplicate_node_ids": duplicate_node_ids,
        "unresolved_import_count": len((graph.get("facts") or {}).get("unresolved_imports") or []),
        "unresolved_import_classes": _classify_unresolved_imports(graph),
        "unresolved_package_roots": unresolved_roots,
        "unmapped_source_file_count": coverage.get("unmapped_source_file_count", 0),
        "unmapped_source_files": coverage.get("unmapped_source_files") or [],
        "relationship_unparsed_file_count": coverage.get("relationship_unparsed_file_count", 0),
        "relationship_unparsed_files": coverage.get("relationship_unparsed_files") or [],
        "relationship_boundary_count": int((graph.get("facts") or {}).get("relationship_boundary_count") or 0),
        "unresolved_relationship_boundary_count": int(
            (graph.get("facts") or {}).get("unresolved_relationship_boundary_count") or 0
        ),
        "relationship_boundary_counts_by_kind": dict(
            (graph.get("facts") or {}).get("relationship_boundary_counts_by_kind") or {}
        ),
        "relationship_boundaries": list((graph.get("facts") or {}).get("relationship_boundaries") or []),
        "evidence_precision_counts": dict((graph.get("facts") or {}).get("evidence_precision_counts") or {}),
        "contract_source_count": int((graph.get("facts") or {}).get("contract_source_count") or 0),
        "contract_declaration_count": int((graph.get("facts") or {}).get("contract_declaration_count") or 0),
        "contract_declaration_counts_by_kind": dict(
            (graph.get("facts") or {}).get("contract_declaration_counts_by_kind") or {}
        ),
        "configuration_key_count": int((graph.get("facts") or {}).get("configuration_key_count") or 0),
        "deployment_fact_count": int((graph.get("facts") or {}).get("deployment_fact_count") or 0),
        "deployment_fact_counts_by_kind": dict(
            (graph.get("facts") or {}).get("deployment_fact_counts_by_kind") or {}
        ),
        "subsystem_count": int((graph.get("facts") or {}).get("subsystem_count") or 0),
        "subsystem_direct_member_counts": dict((graph.get("facts") or {}).get("subsystem_direct_member_counts") or {}),
        "cross_language_subsystem_count": int((graph.get("facts") or {}).get("cross_language_subsystem_count") or 0),
        "cross_language_subsystems": list((graph.get("facts") or {}).get("cross_language_subsystems") or []),
        "build_definition_count": int((graph.get("facts") or {}).get("build_definition_count") or 0),
        "build_definition_counts_by_system": dict((graph.get("facts") or {}).get("build_definition_counts_by_system") or {}),
        "build_input_edge_count": int((graph.get("facts") or {}).get("build_input_edge_count") or 0),
        "governance_boundary_count": int((graph.get("facts") or {}).get("governance_boundary_count") or 0),
        "governance_boundary_counts_by_kind": dict((graph.get("facts") or {}).get("governance_boundary_counts_by_kind") or {}),
        "source_provenance_counts": dict((graph.get("facts") or {}).get("source_provenance_counts") or {}),
        "stale_graph_source_count": coverage.get("stale_graph_source_count", 0),
        "stale_graph_sources": coverage.get("stale_graph_sources") or [],
        "known_violations": known_violations,
        "unacknowledged_blocking_findings": unacknowledged_blocking,
        "note": "Residuals stay visible. An acknowledgement is not a repair. Overlay stays residual until a reviewed relationship is attached.",
    }
    return {
        "schema_version": "1.4",
        "role": "instrument-integrity",
        "integrity_pass": integrity_pass,
        "identity_integrity_pass": not duplicate_node_ids,
        "duplicate_node_ids": duplicate_node_ids,
        "identity_collision_count": duplicate_node_occurrences,
        "undefined_edge_endpoints": missing_endpoints,
        "semantic_findings": findings,
        "unacknowledged_blocking_findings": unacknowledged_blocking,
        "acknowledged_findings": acknowledged,
        "integrity": {
            "identity_integrity_pass": not duplicate_node_ids,
            "duplicate_node_ids": duplicate_node_ids,
            "identity_collision_count": duplicate_node_occurrences,
            "missing_semantic_edge_evidence": sorted(set(missing_edge_evidence)),
            "unacknowledged_blocking_findings": unacknowledged_blocking,
            "acknowledged_semantic_findings": acknowledged,
            "known_violations": known_violations,
            "semantic_finding_count": len(findings),
            "unmapped_source_file_count": coverage.get("unmapped_source_file_count", 0),
            "relationship_unparsed_file_count": coverage.get("relationship_unparsed_file_count", 0),
            "evidence_precision_counts": dict(
                (graph.get("facts") or {}).get("evidence_precision_counts") or {}
            ),
            "unresolved_relationship_boundary_count": int(
                (graph.get("facts") or {}).get("unresolved_relationship_boundary_count") or 0
            ),
            "stale_graph_source_count": coverage.get("stale_graph_source_count", 0),
            "pass": integrity_pass,
        },
        "residuals": residuals,
        "note": "An acknowledgement means the detector already knows the finding. It is not a repair.",
    }
