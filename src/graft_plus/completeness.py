"""Completeness audit with ratchet. Ported from ajenda-ai graph_completeness_audit.py.

An acknowledgement means the detector already knows the finding.
It is not a repair. New unacknowledged blocking findings fail closed.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

TEST_EDGE_TYPES = frozenset({"tests", "tests_function"})
STATIC_EDGE_TYPE = "imports"
SOURCE_NODE_PREFIXES = ("py:", "fe:")

TYPE_BOUNDARY = {
    "runtime": "runtime",
    "security_boundary": "security-boundary",
    "external_service": "external",
    "frontend_module": "frontend",
    "test_module": "tests",
    "database_table": "database",
    "migration": "database-migration",
    "network_egress_sink": "external-egress",
    "http_route": "http-route",
    "state_resource": "state-authority",
    "ci_workflow": "ci",
    "docker": "docker",
    "manifest": "manifest",
    "python_module": None,
}


def architectural_boundary(node: dict[str, Any]) -> str:
    node_type = str(node.get("type") or "")
    mapped = TYPE_BOUNDARY.get(node_type)
    if mapped:
        return mapped
    source = str(node.get("source") or "").replace("\\", "/")
    parts = [part for part in source.split("/") if part]
    if not parts:
        return "source:unknown"
    return f"source:{parts[0]}"


def _production_nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in graph["nodes"] if str(node.get("type")) != "test_module"}


def _production_edges(graph: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        edge
        for edge in graph["edges"]
        if str(edge.get("type")) not in TEST_EDGE_TYPES
        and str(edge.get("from")) in nodes
        and str(edge.get("to")) in nodes
    ]


def _adjacency(node_ids: list[str], edges: list[dict[str, Any]], *, reverse: bool = False) -> dict[str, set[str]]:
    adjacency = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source, target = str(edge["from"]), str(edge["to"])
        if reverse:
            source, target = target, source
        adjacency[source].add(target)
    return adjacency


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    visited = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, set()):
            if target not in visited:
                visited.add(target)
                queue.append(target)
    visited.discard(start)
    return visited


def _betweenness(node_ids: list[str], adjacency: dict[str, set[str]]) -> dict[str, float]:
    centrality = {node_id: 0.0 for node_id in node_ids}
    for source in node_ids:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        shortest_path_count = {node_id: 0.0 for node_id in node_ids}
        shortest_path_count[source] = 1.0
        distance = {node_id: -1 for node_id in node_ids}
        distance[source] = 0
        queue: deque[str] = deque([source])
        while queue:
            current = queue.popleft()
            stack.append(current)
            for target in adjacency[current]:
                if distance[target] < 0:
                    queue.append(target)
                    distance[target] = distance[current] + 1
                if distance[target] == distance[current] + 1:
                    shortest_path_count[target] += shortest_path_count[current]
                    predecessors[target].append(current)
        dependency = {node_id: 0.0 for node_id in node_ids}
        while stack:
            target = stack.pop()
            if shortest_path_count[target]:
                coefficient = (1.0 + dependency[target]) / shortest_path_count[target]
                for predecessor in predecessors[target]:
                    dependency[predecessor] += shortest_path_count[predecessor] * coefficient
            if target != source:
                centrality[target] += dependency[target]
    if len(node_ids) > 2:
        normalization = float((len(node_ids) - 1) * (len(node_ids) - 2))
        centrality = {node_id: value / normalization for node_id, value in centrality.items()}
    return centrality


def _node_metrics(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node_ids = sorted(nodes)
    forward = _adjacency(node_ids, edges)
    reverse = _adjacency(node_ids, edges, reverse=True)
    betweenness = _betweenness(node_ids, forward)
    direct_consumers = Counter(str(edge["to"]) for edge in edges)
    direct_dependencies = Counter(str(edge["from"]) for edge in edges)
    semantic_incident: Counter[str] = Counter()
    for edge in edges:
        if str(edge["type"]) != STATIC_EDGE_TYPE:
            semantic_incident[str(edge["from"])] += 1
            semantic_incident[str(edge["to"])] += 1
    return [
        {
            "id": node_id,
            "boundary": architectural_boundary(nodes[node_id]),
            "direct_consumers": direct_consumers[node_id],
            "direct_dependencies": direct_dependencies[node_id],
            "transitive_consumers": len(_reachable(node_id, reverse)),
            "transitive_dependencies": len(_reachable(node_id, forward)),
            "betweenness": round(betweenness[node_id], 8),
            "semantic_incident_edges": semantic_incident[node_id],
        }
        for node_id in node_ids
    ]


def _boundary_matrix(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for edge in edges:
        source_boundary = architectural_boundary(nodes[str(edge["from"])])
        target_boundary = architectural_boundary(nodes[str(edge["to"])])
        counts[(source_boundary, target_boundary)][str(edge["type"])] += 1
    return [
        {
            "from": source,
            "to": target,
            "count": sum(edge_types.values()),
            "edge_types": dict(sorted(edge_types.items())),
            "cross_boundary": source != target,
        }
        for (source, target), edge_types in sorted(counts.items())
    ]


def _classify_cycles(graph: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for cycle in graph.get("metrics", {}).get("static_cycles") or []:
        members = [str(node_id) for node_id in cycle if str(node_id) in nodes]
        boundaries = sorted({architectural_boundary(nodes[node_id]) for node_id in members})
        result.append(
            {
                "nodes": members,
                "boundaries": boundaries,
                "classification": "cross-boundary" if len(boundaries) > 1 else "intra-boundary",
            }
        )
    return result


def _semantic_reconciliation(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    static_edges = [edge for edge in edges if str(edge["type"]) == STATIC_EDGE_TYPE]
    static_adjacency = _adjacency(sorted(nodes), static_edges)
    reconciled = []
    for edge in edges:
        edge_type = str(edge["type"])
        if edge_type == STATIC_EDGE_TYPE:
            continue
        source, target = str(edge["from"]), str(edge["to"])
        source_backed = source.startswith(SOURCE_NODE_PREFIXES)
        target_backed = target.startswith(SOURCE_NODE_PREFIXES)
        if source_backed and target_backed:
            classification = "static-corroborated" if target in _reachable(source, static_adjacency) else "semantic-only"
        else:
            classification = "boundary-or-external"
        reconciled.append(
            {
                "from": source,
                "to": target,
                "type": edge_type,
                "evidence": edge.get("evidence"),
                "classification": classification,
            }
        )
    return sorted(reconciled, key=lambda item: (str(item["classification"]), str(item["from"]), str(item["to"]), str(item["type"])))


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


def audit(graph: dict[str, Any], overlay: dict[str, Any] | None = None, impact: dict[str, Any] | None = None, subject: Path | None = None) -> dict[str, Any]:
    overlay = overlay or {}
    impact = impact or {}
    known = {str(n["id"]) for n in graph["nodes"]}
    missing_endpoints = sorted(
        {
            str(end)
            for edge in graph["edges"]
            for end in (edge.get("from"), edge.get("to"))
            if end not in known
        }
    )
    nodes = _production_nodes(graph)
    edges = _production_edges(graph, nodes)
    metrics = _node_metrics(nodes, edges) if nodes else []
    boundary_matrix = _boundary_matrix(nodes, edges) if nodes else []
    reconciliation = _semantic_reconciliation(nodes, edges) if nodes else []
    cycles = _classify_cycles(graph, nodes)
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
    integrity_pass = not missing_endpoints and not unacknowledged_blocking and not missing_edge_evidence
    overlay_nodes = [n for n in graph["nodes"] if n.get("layer") == "overlay"]
    unresolved = list((graph.get("facts") or {}).get("unresolved_imports") or [])
    residuals = {
        "overlay": "attached" if overlay_nodes else "residual",
        "unresolved_imports": unresolved,
        "unresolved_package_roots": list((graph.get("facts") or {}).get("unresolved_package_roots") or []),
        "no_git_range": not bool(impact.get("changed_files")),
        "unmapped_changed_files": list(impact.get("unmapped_changed_files") or []),
        "known_violations": known_violations,
        "unacknowledged_blocking_findings": unacknowledged_blocking,
        "note": "Residuals stay visible. An acknowledgement is not a repair. Overlay stays residual until a reviewed relationship is attached.",
    }
    return {
        "schema_version": "1.2",
        "integrity_pass": integrity_pass,
        "undefined_edge_endpoints": missing_endpoints,
        "production_node_count": len(nodes),
        "production_edge_count": len(edges),
        "node_count": graph.get("metrics", {}).get("node_count", len(graph.get("nodes", []))),
        "edge_count": graph.get("metrics", {}).get("edge_count", len(graph.get("edges", []))),
        "boundary_counts": dict(sorted(Counter(architectural_boundary(node) for node in nodes.values()).items())),
        "cross_boundary_edge_count": sum(int(item["count"]) for item in boundary_matrix if item["cross_boundary"]),
        "top_betweenness": sorted(metrics, key=lambda item: (-float(item["betweenness"]), str(item["id"])))[:25],
        "top_transitive_consumers": sorted(metrics, key=lambda item: (-int(item["transitive_consumers"]), str(item["id"])))[:25],
        "boundary_matrix": boundary_matrix,
        "static_cycles": cycles,
        "static_cycle_count": len(cycles),
        "semantic_reconciliation_counts": dict(sorted(Counter(str(item["classification"]) for item in reconciliation).items())),
        "semantic_findings": findings,
        "unacknowledged_blocking_findings": unacknowledged_blocking,
        "acknowledged_findings": acknowledged,
        "integrity": {
            "missing_semantic_edge_evidence": sorted(set(missing_edge_evidence)),
            "unacknowledged_blocking_findings": unacknowledged_blocking,
            "acknowledged_semantic_findings": acknowledged,
            "known_violations": known_violations,
            "semantic_finding_count": len(findings),
            "pass": integrity_pass,
        },
        "residuals": residuals,
        "note": "An acknowledgement means the detector already knows the finding. It is not a repair.",
    }
