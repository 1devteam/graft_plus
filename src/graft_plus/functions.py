"""Participation-based, source-backed Python function topology.

Definitions are collected repository-wide, but only functions that participate
in a proven call, test import, route decoration, entrypoint convention, or an
overlay-selected root are emitted. This keeps topology useful without turning
the artifact into a source dump.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

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


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _decorated(item: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    route_names = {"delete", "get", "head", "options", "patch", "post", "put", "route", "websocket"}
    for decorator in item.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (_call_name(target) or "").rsplit(".", 1)[-1].lower() in route_names:
            return True
    return False


def _production_sources(subject: Path, python_sources: set[str]) -> list[Path]:
    return [
        subject / source
        for source in sorted(python_sources)
        if not ({"test", "tests", "fixtures", "migrations", "alembic"} & set(Path(source).parts))
        and (subject / source).is_file()
    ]


def _from_module(current: str, path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package = current.split(".") if path.name == "__init__.py" else current.split(".")[:-1]
    ascend = node.level - 1
    if ascend > len(package):
        return None
    base = package[: len(package) - ascend]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def collect_function_graph(
    subject: Path,
    overlay: dict[str, Any],
    python_by_source: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Emit only functions participating in statically proven topology."""
    roots = _root_values(overlay)
    definitions: dict[tuple[str, str], dict[str, Any]] = {}
    trees: dict[Path, ast.Module] = {}
    imported_names: dict[tuple[str, str], tuple[str, str]] = {}
    imported_modules: dict[tuple[str, str], str] = {}

    for path in _production_sources(subject, set(python_by_source)):
        source = rel(subject, path)
        module = _module_for(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        trees[path] = tree
        for item in tree.body:
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imported_modules[(module, alias.asname or alias.name.split(".", 1)[0])] = alias.name
            if isinstance(item, ast.ImportFrom):
                imported_module = _from_module(module, path, item)
                if not imported_module:
                    continue
                for alias in item.names:
                    imported_names[(module, alias.asname or alias.name)] = (imported_module, alias.name)
                    imported_modules[(module, alias.asname or alias.name)] = f"{imported_module}.{alias.name}"
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            key = (module, item.name)
            definitions[key] = {
                "id": f"fn:{module}:{item.name}",
                "type": "python_function",
                "source": source,
                "layer": "generated",
                "name": item.name,
                "module": module,
                "start_line": item.lineno,
                "end_line": getattr(item, "end_lineno", item.lineno),
                "async": isinstance(item, ast.AsyncFunctionDef),
                "detector": "python_ast",
                "route_handler": _decorated(item),
            }

    call_edges: list[dict[str, Any]] = []
    participants: set[tuple[str, str]] = set()
    for path, tree in trees.items():
        source = rel(subject, path)
        module = _module_for(subject, path)
        for item in tree.body:
            caller_key = (module, getattr(item, "name", ""))
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or caller_key not in definitions:
                continue
            for call in (node for node in ast.walk(item) if isinstance(node, ast.Call)):
                called = _call_name(call.func)
                if not called:
                    continue
                target_key = ("", "")
                if isinstance(call.func, ast.Name):
                    target_key = (module, call.func.id)
                    if target_key not in definitions:
                        target_key = imported_names.get((module, call.func.id), ("", ""))
                elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                    imported_module = imported_modules.get((module, call.func.value.id))
                    if imported_module:
                        target_key = (imported_module, call.func.attr)
                if target_key not in definitions or target_key == caller_key:
                    continue
                participants.update((caller_key, target_key))
                call_edges.append(
                    {
                        "from": definitions[caller_key]["id"],
                        "to": definitions[target_key]["id"],
                        "type": "calls_function",
                        "evidence": source,
                        "start_line": call.lineno,
                        "end_line": getattr(call, "end_lineno", call.lineno),
                        "symbol": called,
                        "detector": "python_ast",
                        "layer": "generated",
                    }
                )

    test_edges: list[dict[str, Any]] = []
    for path in subject.rglob("*.py"):
        source = rel(subject, path)
        if skipped(subject, path) or not ({"test", "tests"} & set(Path(source).parts)):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for item in ast.walk(tree):
            if not isinstance(item, ast.ImportFrom) or item.level or not item.module:
                continue
            for alias in item.names:
                key = (item.module, alias.name)
                if key not in definitions:
                    continue
                participants.add(key)
                test_edges.append(
                    {
                        "from": f"test:{source}",
                        "to": definitions[key]["id"],
                        "type": "tests_function",
                        "evidence": source,
                        "start_line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "symbol": alias.name,
                        "detector": "python_ast",
                        "layer": "generated",
                    }
                )

    participants.update(
        key
        for key, node in definitions.items()
        if node["route_handler"]
        or node["name"] == "main"
        or any(node["source"] == root or str(node["source"]).startswith(root + "/") for root in roots)
    )
    nodes = [definitions[key] for key in sorted(participants)]
    emitted = {str(node["id"]) for node in nodes}
    edges = [
        edge
        for edge in [*call_edges, *test_edges]
        if edge["to"] in emitted and (edge["from"] in emitted or edge["type"] == "tests_function")
    ]
    for key in sorted(participants):
        node = definitions[key]
        parent = python_by_source.get(str(node["source"]))
        if parent:
            edges.append(
                {
                    "from": parent,
                    "to": node["id"],
                    "type": "defines_function",
                    "evidence": node["source"],
                    "start_line": node["start_line"],
                    "end_line": node["end_line"],
                    "symbol": node["name"],
                    "detector": "python_ast",
                    "layer": "generated",
                }
            )
    unique = {tuple(sorted(edge.items())): edge for edge in edges}
    return nodes, sorted(unique.values(), key=lambda item: (str(item["from"]), str(item["to"]), str(item["type"])))
