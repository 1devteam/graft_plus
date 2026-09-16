"""Opt-in, source-backed Python function topology.

Function graphs are useful inside orchestration and other composition roots, but
expanding every function in every repository creates more noise than evidence.
Subjects select roots in their overlay with ``function_roots``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from graft_plus.graph_types import StaticEdge
from graft_plus.inventory import rel, skipped


def _module_for(subject: Path, path: Path) -> str:
    parts = list(path.relative_to(subject).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _root_values(overlay: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in overlay.get("function_roots") or []:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            value = item.get("path") or item.get("source")
            if isinstance(value, str):
                values.append(value)
    return sorted(set(value.strip("/") for value in values if value.strip("/")))


def _selected_sources(subject: Path, overlay: dict[str, Any], python_sources: set[str]) -> list[Path]:
    roots = _root_values(overlay)
    if not roots:
        return []
    selected = []
    for source in sorted(python_sources):
        if any(source == root or source.startswith(root + "/") for root in roots):
            path = subject / source
            if path.is_file() and not skipped(subject, path):
                selected.append(path)
    return selected


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def collect_function_graph(
    subject: Path,
    overlay: dict[str, Any],
    python_by_source: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect declared functions, direct calls, and exact test imports."""
    selected = _selected_sources(subject, overlay, set(python_by_source))
    if not selected:
        return [], []

    functions: dict[tuple[str, str], dict[str, Any]] = {}
    trees: dict[Path, ast.Module] = {}
    for path in selected:
        source = rel(subject, path)
        module = _module_for(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        trees[path] = tree
        for item in tree.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            function_id = f"fn:{module}:{item.name}"
            functions[(module, item.name)] = {
                "id": function_id,
                "type": "python_function",
                "source": source,
                "layer": "generated",
                "name": item.name,
                "module": module,
                "line": item.lineno,
                "async": isinstance(item, ast.AsyncFunctionDef),
            }

    edges: set[StaticEdge] = set()
    by_name: dict[str, list[tuple[str, str]]] = {}
    for key in functions:
        by_name.setdefault(key[1], []).append(key)
        module, name = key
        source = str(functions[key]["source"])
        parent = python_by_source.get(source)
        if parent:
            edges.add(StaticEdge(parent, f"fn:{module}:{name}", "defines_function", source))

    for path, tree in trees.items():
        source = rel(subject, path)
        module = _module_for(subject, path)
        for item in tree.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or (module, item.name) not in functions:
                continue
            caller = f"fn:{module}:{item.name}"
            for call in (node for node in ast.walk(item) if isinstance(node, ast.Call)):
                called = _call_name(call.func)
                if not called:
                    continue
                short = called.rsplit(".", 1)[-1]
                local = (module, short)
                candidates = [local] if local in functions else by_name.get(short, [])
                if len(candidates) == 1:
                    target_module, target_name = candidates[0]
                    target = f"fn:{target_module}:{target_name}"
                    if target != caller:
                        edges.add(StaticEdge(caller, target, "calls_function", source))

    for path in subject.rglob("*.py"):
        source = rel(subject, path)
        if skipped(subject, path) or not (source.startswith("tests/") or "/tests/" in source):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        test_id = f"test:{source}"
        for item in ast.walk(tree):
            if not isinstance(item, ast.ImportFrom) or item.level or not item.module:
                continue
            for alias in item.names:
                key = (item.module, alias.name)
                if key in functions:
                    edges.add(StaticEdge(test_id, str(functions[key]["id"]), "tests_function", source))

    return sorted(functions.values(), key=lambda item: str(item["id"])), [
        {"from": edge.source, "to": edge.target, "type": edge.type, "evidence": edge.evidence, "layer": "generated"}
        for edge in sorted(edges, key=lambda item: (item.source, item.target, item.type))
    ]
