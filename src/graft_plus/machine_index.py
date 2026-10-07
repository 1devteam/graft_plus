"""Precomputed machine-oriented graph indexes.

These are descriptive graph facts, not plans or recommendations. They reduce the
reasoning work required by downstream models by exposing high-signal topology
without forcing a full graph scan for common questions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

STRUCTURAL_EDGE_TYPES = frozenset({
    "member_of_subsystem",
    "governs_build_of",
    "governs_boundary_of",
    "declared_in",
    "defines_function",
    "defines_contract",
})


def _node_row(node: dict[str, Any], count: int, *, field: str) -> dict[str, Any]:
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "source": str(node.get("source") or ""),
        field: count,
    }


def _top(counter: Counter[str], nodes: dict[str, dict[str, Any]], field: str, limit: int = 64) -> list[dict[str, Any]]:
    rows = []
    for node_id, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]:
        node = nodes.get(node_id)
        if node is not None:
            rows.append(_node_row(node, count, field=field))
    return rows


def build_machine_index(graph: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    node_rows = [dict(node) for node in graph.get("nodes") or []]
    edge_rows = [dict(edge) for edge in graph.get("edges") or []]
    nodes = {str(node.get("id") or ""): node for node in node_rows}
    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    dep_in: Counter[str] = Counter()
    dep_out: Counter[str] = Counter()
    cross_subsystem: Counter[tuple[str, str, str]] = Counter()

    for edge in edge_rows:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        edge_type = str(edge.get("type") or "")
        fan_out[source] += 1
        fan_in[target] += 1
        if edge_type not in STRUCTURAL_EDGE_TYPES:
            dep_out[source] += 1
            dep_in[target] += 1
        source_subsystem = str(nodes.get(source, {}).get("subsystem") or "")
        target_subsystem = str(nodes.get(target, {}).get("subsystem") or "")
        if source_subsystem and target_subsystem and source_subsystem != target_subsystem:
            cross_subsystem[(source_subsystem, target_subsystem, edge_type)] += 1

    incident = set(fan_in) | set(fan_out)
    isolated = sorted(node_id for node_id in nodes if node_id not in incident)
    node_type_counts = Counter(str(node.get("type") or "unknown") for node in node_rows)
    edge_type_counts = Counter(str(edge.get("type") or "unknown") for edge in edge_rows)

    contracts = Counter({
        node_id: dep_in.get(node_id, 0)
        for node_id, node in nodes.items()
        if node.get("type") in {"contract", "contract_source"} and dep_in.get(node_id, 0)
    })
    build_nodes = Counter({
        node_id: dep_out.get(node_id, 0)
        for node_id, node in nodes.items()
        if node.get("type") in {"build_definition", "build_target"} and dep_out.get(node_id, 0)
    })
    crossings = [
        {
            "from_subsystem": source,
            "to_subsystem": target,
            "edge_type": edge_type,
            "count": count,
        }
        for (source, target, edge_type), count in sorted(
            cross_subsystem.items(),
            key=lambda item: (-item[1], item[0]),
        )[:128]
    ]

    return {
        "schema_version": "1.0",
        "product": "G.R.A.F.T.+",
        "role": "machine-topology-index",
        "direction": "consumer-to-dependency",
        "node_count": len(node_rows),
        "edge_count": len(edge_rows),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "top_fan_in": _top(fan_in, nodes, "fan_in"),
        "top_fan_out": _top(fan_out, nodes, "fan_out"),
        "top_dependency_fan_in": _top(dep_in, nodes, "dependency_fan_in"),
        "top_dependency_fan_out": _top(dep_out, nodes, "dependency_fan_out"),
        "contract_hubs": _top(contracts, nodes, "dependency_fan_in", limit=32),
        "build_hubs": _top(build_nodes, nodes, "dependency_fan_out", limit=32),
        "cross_subsystem_edges": crossings,
        "isolated_node_count": len(isolated),
        "isolated_node_sample": isolated[:128],
        "unresolved": {
            "reference_count": ledger.get("reference_count", 0),
            "unique_specifier_count": ledger.get("unique_specifier_count", 0),
            "unique_source_count": ledger.get("unique_source_count", 0),
            "class_counts": ledger.get("class_counts", {}),
            "top_specifiers": ledger.get("top_specifiers", []),
            "top_sources": ledger.get("top_sources", []),
        },
        "negatives": [
            "High degree is a structural signal, not a defect.",
            "A hub is not a refactor recommendation.",
            "Cross-subsystem traffic is evidence of coupling, not proof of improper coupling.",
        ],
    }
}
