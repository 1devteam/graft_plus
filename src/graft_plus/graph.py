"""Static inventory: Python, TypeScript, tests, overlay."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FRONTEND_IMPORT_RE = re.compile(r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]")
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache"}


@dataclass(frozen=True, slots=True)
class StaticNode:
    id: str
    type: str
    source: str


@dataclass(frozen=True, slots=True)
class StaticEdge:
    source: str
    target: str
    type: str
    evidence: str


def _skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def discover_python_roots(subject: Path) -> list[Path]:
    candidates = [subject / "src", subject / "backend", subject / "lib", subject / "pkg"]
    found = [p for p in candidates if p.is_dir()]
    if found:
        return found
    py = [p for p in subject.glob("*.py") if p.name != "setup.py"]
    return [subject] if py else []


def discover_frontend_roots(subject: Path) -> list[Path]:
    candidates = [subject / "frontend" / "src", subject / "src"]
    return [p for p in candidates if p.is_dir() and any(p.rglob("*.ts"))]


def _module_for(subject: Path, path: Path) -> str:
    rel = path.relative_to(subject).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _python_files(roots: list[Path], subject: Path) -> dict[Path, str]:
    files: dict[Path, str] = {}
    for root in roots:
        for path in root.rglob("*.py"):
            if _skip(path):
                continue
            files[path] = _module_for(subject, path)
    return files


def _best_target(imported: str, modules: set[str]) -> str | None:
    if imported in modules:
        return imported
    parts = imported.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
    return None


def _resolve_from(current: str, is_package: bool, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    parts = current.split(".")
    package = parts if is_package else parts[:-1]
    ascend = max(node.level - 1, 0)
    if ascend > len(package):
        return None
    base = package[: len(package) - ascend]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def collect_python_graph(subject: Path, roots: list[Path]) -> tuple[list[StaticNode], list[StaticEdge]]:
    module_by_path = _python_files(roots, subject)
    modules = set(module_by_path.values())
    prefixes = tuple({m.split(".")[0] for m in modules if m})
    nodes = [
        StaticNode(id=f"py:{module}", type="python_module", source=str(path.relative_to(subject)).replace("\\\\", "/"))
        for path, module in module_by_path.items()
        if module
    ]
    edges: set[StaticEdge] = set()
    for path, module in module_by_path.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        is_package = path.name == "__init__.py"
        imported: set[str] = set()
        for item in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(item, ast.Import):
                candidates.extend(alias.name for alias in item.names)
            elif isinstance(item, ast.ImportFrom):
                base = _resolve_from(module, is_package, item)
                if base:
                    candidates.append(base)
                    candidates.extend(f"{base}.{alias.name}" for alias in item.names if alias.name != "*")
            for name in candidates:
                if prefixes and not name.startswith(prefixes):
                    continue
                target = _best_target(name, modules)
                if target and target != module:
                    imported.add(target)
        rel = str(path.relative_to(subject)).replace("\\\\", "/")
        for target in imported:
            edges.add(StaticEdge(source=f"py:{module}", target=f"py:{target}", type="imports", evidence=rel))
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type))


def collect_test_graph(subject: Path, production_modules: set[str]) -> tuple[list[StaticNode], list[StaticEdge]]:
    tests_root = subject / "tests"
    if not tests_root.is_dir():
        return [], []
    prefixes = tuple({m.split(".")[0] for m in production_modules if m})
    nodes: list[StaticNode] = []
    edges: set[StaticEdge] = set()
    for path in tests_root.rglob("*.py"):
        rel_under_tests = path.relative_to(tests_root)
        if _skip(path) or "fixtures" in rel_under_tests.parts:
            continue
        rel = str(path.relative_to(subject)).replace("\\\\", "/")
        node_id = f"test:{rel}"
        nodes.append(StaticNode(id=node_id, type="test_module", source=rel))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for item in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(item, ast.Import):
                candidates.extend(alias.name for alias in item.names)
            elif isinstance(item, ast.ImportFrom) and item.level == 0 and item.module:
                candidates.append(item.module)
            for name in candidates:
                if prefixes and not name.startswith(prefixes):
                    continue
                target = _best_target(name, production_modules)
                if target:
                    edges.add(StaticEdge(source=node_id, target=f"py:{target}", type="tests", evidence=rel))
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type))


def _fe_id(subject: Path, path: Path) -> str:
    return "fe:" + str(path.relative_to(subject)).replace("\\\\", "/")


def collect_frontend_graph(subject: Path, roots: list[Path]) -> tuple[list[StaticNode], list[StaticEdge]]:
    files: set[Path] = set()
    for root in roots:
        files.update(p.resolve() for p in root.rglob("*") if p.suffix in {".ts", ".tsx"} and not _skip(p))
    nodes = [
        StaticNode(id=_fe_id(subject, path), type="frontend_module", source=str(path.relative_to(subject)).replace("\\\\", "/"))
        for path in sorted(files)
    ]
    edges: set[StaticEdge] = set()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in FRONTEND_IMPORT_RE.finditer(text):
            spec = match.group(1)
            if not spec.startswith("."):
                continue
            raw = (path.parent / spec).resolve()
            candidates = [raw, raw.with_suffix(".ts"), raw.with_suffix(".tsx"), raw / "index.ts", raw / "index.tsx"]
            target = next((c for c in candidates if c in files), None)
            if target and target != path:
                edges.add(
                    StaticEdge(
                        source=_fe_id(subject, path),
                        target=_fe_id(subject, target),
                        type="imports",
                        evidence=str(path.relative_to(subject)).replace("\\\\", "/"),
                    )
                )
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type))


def _tarjan(nodes: list[str], pairs: list[tuple[str, str]]) -> list[list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for s, t in pairs:
        adj[s].append(t)
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    low: dict[str, int] = {}
    components: list[list[str]] = []

    def connect(node: str) -> None:
        nonlocal index
        indexes[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adj[node]:
            if target not in indexes:
                connect(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indexes[target])
        if low[node] != indexes[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for node in nodes:
        if node not in indexes:
            connect(node)
    return sorted(components, key=lambda c: (-len(c), c))


def _metrics(node_ids: list[str], edges: list[dict[str, Any]]) -> dict[str, Any]:
    fan_in: dict[str, int] = defaultdict(int)
    fan_out: dict[str, int] = defaultdict(int)
    types: Counter[str] = Counter()
    pairs: list[tuple[str, str]] = []
    for edge in edges:
        src, dst, kind = str(edge["from"]), str(edge["to"]), str(edge["type"])
        fan_out[src] += 1
        fan_in[dst] += 1
        types[kind] += 1
        if kind == "imports":
            pairs.append((src, dst))
    ranked = lambda counts: [{"node": n, "count": c} for n, c in sorted(((n, counts[n]) for n in node_ids), key=lambda i: (-i[1], i[0]))[:25] if c]
    return {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "edge_counts_by_type": dict(sorted(types.items())),
        "top_fan_in": ranked(fan_in),
        "top_fan_out": ranked(fan_out),
        "static_cycles": _tarjan(node_ids, pairs),
    }


def load_overlay(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"schema_version": "1.0", "nodes": [], "edges": [], "invariants": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("overlay root must be an object")
    return payload


def build_graph(*, subject: Path, overlay_path: Path | None = None) -> dict[str, Any]:
    subject = subject.resolve()
    py_roots = discover_python_roots(subject)
    fe_roots = discover_frontend_roots(subject)
    py_nodes, py_edges = collect_python_graph(subject, py_roots)
    fe_nodes, fe_edges = collect_frontend_graph(subject, fe_roots)
    production = {n.id[3:] for n in py_nodes}
    test_nodes, test_edges = collect_test_graph(subject, production)
    overlay = load_overlay(overlay_path)

    nodes: list[dict[str, Any]] = [{"id": n.id, "type": n.type, "source": n.source} for n in [*py_nodes, *fe_nodes, *test_nodes]]
    nodes.extend(overlay.get("nodes") or [])
    edges: list[dict[str, Any]] = [
        {"from": e.source, "to": e.target, "type": e.type, "evidence": e.evidence}
        for e in [*py_edges, *fe_edges, *test_edges]
    ]
    edges.extend(overlay.get("edges") or [])

    ids = [str(n["id"]) for n in nodes]
    dupes = sorted(i for i, c in Counter(ids).items() if c > 1)
    if dupes:
        raise ValueError(f"duplicate nodes: {', '.join(dupes)}")
    known = set(ids)
    missing = sorted({str(x) for e in edges for x in (e.get("from"), e.get("to")) if x not in known})
    if missing:
        raise ValueError(f"edges reference undefined nodes: {', '.join(missing)}")
    node_ids = sorted(known)
    overlay_rel = None
    if overlay_path and overlay_path.exists():
        try:
            overlay_rel = str(overlay_path.resolve().relative_to(subject))
        except ValueError:
            overlay_rel = str(overlay_path)
    return {
        "schema_version": "1.0",
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "role": "fact-substrate",
        "implementsPlan": False,
        "grants_execution_authority": False,
        "generated_from": {
            "python_roots": [str(p.relative_to(subject)) if p != subject else "." for p in py_roots],
            "frontend_roots": [str(p.relative_to(subject)) for p in fe_roots],
            "overlay": overlay_rel,
        },
        "nodes": sorted(nodes, key=lambda n: str(n["id"])),
        "edges": sorted(edges, key=lambda e: (str(e["from"]), str(e["to"]), str(e["type"]))),
        "invariants": overlay.get("invariants") or [],
        "metrics": _metrics(node_ids, edges),
    }
