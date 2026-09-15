"""Map a git path range onto graph nodes."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


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


def analyze_impact(graph: dict[str, Any], changed: list[str]) -> dict[str, Any]:
    source_index: dict[str, list[str]] = defaultdict(list)
    nodes = {str(n["id"]): n for n in graph["nodes"]}
    for node in graph["nodes"]:
        source = node.get("source")
        if isinstance(source, str) and source:
            source_index[_normalize(source)].append(str(node["id"]))
    changed_nodes: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for path in changed:
        ids = source_index.get(path, [])
        if not ids:
            unmapped.append(path)
            continue
        for node_id in ids:
            changed_nodes.append(nodes[node_id])
    consumers: dict[str, list[str]] = defaultdict(list)
    for edge in graph["edges"]:
        consumers[str(edge["to"])].append(str(edge["from"]))
    impacted_tests: list[str] = []
    seen = {str(n["id"]) for n in changed_nodes}
    stack = list(seen)
    while stack:
        current = stack.pop()
        for src in consumers.get(current, []):
            if src in seen:
                continue
            seen.add(src)
            stack.append(src)
            node = nodes.get(src)
            if node and node.get("type") == "test_module":
                impacted_tests.append(src)
    return {
        "schema_version": "1.0",
        "changed_files": changed,
        "changed_nodes": sorted(changed_nodes, key=lambda n: str(n["id"])),
        "unmapped_changed_files": unmapped,
        "impacted_tests": sorted(set(impacted_tests)),
        "changed_node_count": len(changed_nodes),
        "changed_file_count": len(changed),
        "unmapped_changed_file_count": len(unmapped),
        "impacted_test_count": len(set(impacted_tests)),
    }
