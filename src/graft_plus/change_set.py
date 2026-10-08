"""Factual git-range mapping for G.R.A.F.T.+.

This module records only directly observable change facts:
- the requested git refs and resolved commit SHAs;
- files changed between those refs;
- graph nodes whose source field directly names a changed file;
- changed files with no direct graph-node mapping.

It intentionally performs no reachability, blast-radius, proof selection, risk
classification, architectural judgment, or recommendation.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

CHANGE_SET_FILE = "graph-change-set.v1.json"


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def _git(subject: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=subject,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return result.stdout.strip()


def resolve_ref(subject: Path, ref: str) -> str:
    """Resolve a git ref to the exact commit SHA used by the change set."""

    return _git(subject, "rev-parse", f"{ref}^{{commit}}")


def changed_files(subject: Path, base_ref: str, head_ref: str) -> list[str]:
    """Return repository-relative files changed by base...head."""

    output = _git(subject, "diff", "--name-only", f"{base_ref}...{head_ref}")
    return sorted({_normalize(line) for line in output.splitlines() if line.strip()})


def _source_index(graph: dict[str, Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for node in graph.get("nodes") or []:
        source = node.get("source")
        node_id = node.get("id")
        if isinstance(source, str) and source and node_id:
            index[_normalize(source)].append(str(node_id))
    return {
        source: sorted(set(node_ids))
        for source, node_ids in sorted(index.items())
    }


def build_change_set(
    graph: dict[str, Any],
    subject: Path,
    base_ref: str | None,
    head_ref: str | None,
) -> dict[str, Any]:
    """Build a direct, non-transitive change-set observation."""

    if bool(base_ref) != bool(head_ref):
        raise ValueError("--base-ref and --head-ref must be provided together")

    if not base_ref or not head_ref:
        return {
            "schema_version": "1.0",
            "role": "factual-change-set",
            "requested": False,
            "base_ref": None,
            "head_ref": None,
            "base_sha": None,
            "head_sha": None,
            "changed_files": [],
            "direct_node_mappings": [],
            "changed_node_ids": [],
            "unmapped_changed_files": [],
            "changed_file_count": 0,
            "changed_node_count": 0,
            "unmapped_changed_file_count": 0,
        }

    files = changed_files(subject, base_ref, head_ref)
    source_index = _source_index(graph)
    mappings = [
        {"source": source, "node_ids": source_index[source]}
        for source in files
        if source in source_index
    ]
    node_ids = sorted({
        node_id
        for mapping in mappings
        for node_id in mapping["node_ids"]
    })
    unmapped = sorted(source for source in files if source not in source_index)

    return {
        "schema_version": "1.0",
        "role": "factual-change-set",
        "requested": True,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "base_sha": resolve_ref(subject, base_ref),
        "head_sha": resolve_ref(subject, head_ref),
        "changed_files": files,
        "direct_node_mappings": mappings,
        "changed_node_ids": node_ids,
        "unmapped_changed_files": unmapped,
        "changed_file_count": len(files),
        "changed_node_count": len(node_ids),
        "unmapped_changed_file_count": len(unmapped),
    }
