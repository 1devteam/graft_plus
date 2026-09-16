"""Blast radius. Ported from ajenda-ai scripts/validation/graph_impact_analysis.py.

Consumer -> dependency. Reverse walk = what a change can affect.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict, deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TEST_EDGE_TYPES = frozenset({"tests", "tests_function"})
TEST_NODE_TYPE = "test_module"
SEMANTIC_NODE_TYPES = frozenset(
    {
        "database_table",
        "migration",
        "network_egress_sink",
        "http_route",
        "security_boundary",
        "external_service",
        "state_resource",
        "runtime",
        "business_job",
        "runtime_artifact",
        "runtime_input",
        "runtime_action",
    }
)


def _normalize(path: str) -> str:
    n = path.replace("\\", "/")
    return n[2:] if n.startswith("./") else n


def changed_files(subject: Path, base_ref: str, head_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        cwd=subject,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"unable to diff {base_ref}...{head_ref}")
    return sorted({_normalize(line) for line in result.stdout.splitlines() if line.strip()})


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in graph["nodes"]}


def _source_index(graph: dict[str, Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for node in graph["nodes"]:
        source = node.get("source")
        if isinstance(source, str) and source:
            index[_normalize(source)].append(str(node["id"]))
    return {source: sorted(ids) for source, ids in index.items()}


def _production_edges(graph: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edges = []
    for edge in graph["edges"]:
        source, target = str(edge["from"]), str(edge["to"])
        if str(edge["type"]) in TEST_EDGE_TYPES:
            continue
        if nodes.get(source, {}).get("type") == TEST_NODE_TYPE or nodes.get(target, {}).get("type") == TEST_NODE_TYPE:
            continue
        edges.append(edge)
    return edges


def _adjacency(edges: Iterable[dict[str, Any]], *, reverse: bool) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source, target = str(edge["from"]), str(edge["to"])
        if reverse:
            source, target = target, source
        adjacency[source].add(target)
    return adjacency


def _distances(starts: Iterable[str], adjacency: dict[str, set[str]]) -> dict[str, int]:
    distance: dict[str, int] = {}
    queue: deque[str] = deque()
    for start in sorted(set(starts)):
        distance[start] = 0
        queue.append(start)
    while queue:
        current = queue.popleft()
        for target in sorted(adjacency.get(current, set())):
            if target in distance:
                continue
            distance[target] = distance[current] + 1
            queue.append(target)
    return distance


def _described(distances: dict[str, int], nodes: dict[str, dict[str, Any]], exclude: set[str]) -> list[dict[str, Any]]:
    out = []
    for node_id, distance in distances.items():
        if node_id in exclude:
            continue
        node = nodes.get(node_id) or {}
        out.append(
            {
                "id": node_id,
                "type": node.get("type"),
                "source": node.get("source"),
                "label": node.get("label"),
                "distance": distance,
            }
        )
    return sorted(out, key=lambda item: (int(item["distance"]), str(item["id"])))


def _impacted_tests(graph: dict[str, Any], nodes: dict[str, dict[str, Any]], affected: set[str]) -> list[str]:
    tests: set[str] = set()
    for edge in graph["edges"]:
        if str(edge["type"]) not in TEST_EDGE_TYPES:
            continue
        if str(edge["to"]) in affected:
            tests.add(str(edge["from"]))
    return sorted(tests)


def _semantic(node_ids: set[str], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for node_id in sorted(node_ids):
        node = nodes.get(node_id) or {}
        if node.get("type") not in SEMANTIC_NODE_TYPES:
            continue
        selected.append({"id": node_id, "type": node.get("type"), "source": node.get("source"), "label": node.get("label")})
    return selected


def analyze_impact(graph: dict[str, Any], changed: list[str]) -> dict[str, Any]:
    changed = sorted({_normalize(path) for path in changed})
    nodes = _node_map(graph)
    source_index = _source_index(graph)
    changed_node_ids = sorted({node_id for path in changed for node_id in source_index.get(path, [])})
    unmapped = sorted(path for path in changed if path not in source_index)
    changed_production = {node_id for node_id in changed_node_ids if nodes.get(node_id, {}).get("type") != TEST_NODE_TYPE}
    production_edges = _production_edges(graph, nodes)
    upstream = _distances(changed_production, _adjacency(production_edges, reverse=True))
    downstream = _distances(changed_production, _adjacency(production_edges, reverse=False))
    upstream_ids = set(upstream) - changed_production
    downstream_ids = set(downstream) - changed_production
    affected = changed_production | upstream_ids
    impacted = _impacted_tests(graph, nodes, affected)
    changed_nodes = [nodes[node_id] for node_id in changed_node_ids]
    return {
        "schema_version": "1.2",
        "changed_files": changed,
        "changed_nodes": changed_nodes,
        "unmapped_changed_files": unmapped,
        "upstream_consumers": _described(upstream, nodes, changed_production),
        "downstream_dependencies": _described(downstream, nodes, changed_production),
        "impacted_tests": impacted,
        "affected_semantic_nodes": _semantic(affected, nodes),
        "dependency_semantic_nodes": _semantic(downstream_ids, nodes),
        "changed_node_count": len(changed_node_ids),
        "changed_file_count": len(changed),
        "unmapped_changed_file_count": len(unmapped),
        "impacted_test_count": len(impacted),
        "note": "consumer->dependency; reverse walk is blast radius",
    }
