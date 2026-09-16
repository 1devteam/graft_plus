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
RUNTIME_ROOTS = {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "concurrent", "configparser",
    "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal", "email", "enum",
    "fnmatch", "functools", "getpass", "glob", "gzip", "hashlib", "hmac", "html", "http",
    "importlib", "inspect", "io", "itertools", "json", "logging", "math", "mmap",
    "multiprocessing", "os", "pathlib", "pickle", "pkgutil", "platform", "pprint", "queue",
    "random", "re", "secrets", "shutil", "signal", "socket", "sqlite3", "ssl", "statistics",
    "string", "struct", "subprocess", "sys", "tarfile", "tempfile", "textwrap", "threading",
    "time", "tomllib", "traceback", "types", "typing", "unicodedata", "unittest", "urllib",
    "uuid", "warnings", "weakref", "webbrowser", "xml", "zipfile", "__future__",
    "node:fs", "node:path", "node:url", "node:test", "node:crypto", "node:assert",
}


def _rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def _runtime(specifier: str) -> bool:
    root = specifier.split(".")[0].split("/")[0]
    return root in RUNTIME_ROOTS or specifier.startswith("node:")


def _package_root(specifier: str) -> str:
    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split(".")[0].split("/")[0]


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
    found: list[Path] = []
    for name in ("src", "backend", "lib", "pkg"):
        path = subject / name
        if path.is_dir():
            found.append(path)
    skip_top = SKIP_DIRS | {"tests", "docs", "examples", "scripts", "migrations"}
    for child in sorted(subject.iterdir()):
        if not child.is_dir() or child.name in skip_top or _skip(child):
            continue
        if (child / "__init__.py").exists() and child not in found:
            found.append(child)
    if found:
        return found
    py = [p for p in subject.glob("*.py") if p.name not in {"setup.py", "conftest.py"}]
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


def collect_python_graph(subject: Path, roots: list[Path]) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    module_by_path = _python_files(roots, subject)
    modules = set(module_by_path.values())
    nodes = [
        StaticNode(id=f"py:{module}", type="python_module", source=_rel(subject, path))
        for path, module in module_by_path.items()
        if module
    ]
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path, module in module_by_path.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        is_package = path.name == "__init__.py"
        imported: set[str] = set()
        rel = _rel(subject, path)
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
                target = _best_target(name, modules)
                if target and target != module:
                    imported.add(target)
                elif not target and not _runtime(name):
                    unresolved.append({"specifier": name, "from": rel})
        for target in imported:
            edges.add(StaticEdge(source=f"py:{module}", target=f"py:{target}", type="imports", evidence=rel))
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type)), unresolved


def collect_test_graph(subject: Path, production_modules: set[str]) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    tests_root = subject / "tests"
    if not tests_root.is_dir():
        return [], [], []
    nodes: list[StaticNode] = []
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path in tests_root.rglob("*.py"):
        rel_under_tests = path.relative_to(tests_root)
        if _skip(path) or "fixtures" in rel_under_tests.parts:
            continue
        rel = _rel(subject, path)
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
                target = _best_target(name, production_modules)
                if target:
                    edges.add(StaticEdge(source=node_id, target=f"py:{target}", type="tests", evidence=rel))
                elif not _runtime(name):
                    unresolved.append({"specifier": name, "from": rel})
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type)), unresolved


def _fe_id(subject: Path, path: Path) -> str:
    return "fe:" + _rel(subject, path)


def collect_frontend_graph(subject: Path, roots: list[Path]) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    files: set[Path] = set()
    for root in roots:
        files.update(p.resolve() for p in root.rglob("*") if p.suffix in {".ts", ".tsx"} and not _skip(p))
    nodes = [
        StaticNode(id=_fe_id(subject, path), type="frontend_module", source=_rel(subject, path))
        for path in sorted(files)
    ]
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = _rel(subject, path)
        for match in FRONTEND_IMPORT_RE.finditer(text):
            spec = match.group(1)
            if spec.startswith("."):
                raw = (path.parent / spec).resolve()
                candidates = [raw, raw.with_suffix(".ts"), raw.with_suffix(".tsx"), raw / "index.ts", raw / "index.tsx"]
                target = next((c for c in candidates if c in files), None)
                if target and target != path:
                    edges.add(
                        StaticEdge(
                            source=_fe_id(subject, path),
                            target=_fe_id(subject, target),
                            type="imports",
                            evidence=rel,
                        )
                    )
                elif not target:
                    unresolved.append({"specifier": spec, "from": rel})
            elif not _runtime(spec):
                unresolved.append({"specifier": spec, "from": rel})
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type)), unresolved


def collect_surfaces(subject: Path) -> list[StaticNode]:
    nodes: list[StaticNode] = []
    for path in subject.rglob("*"):
        if not path.is_file() or _skip(path):
            continue
        rel = _rel(subject, path)
        name = path.name
        if rel.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
            nodes.append(StaticNode(id=f"ci:{rel}", type="ci_workflow", source=rel))
        elif name == "Dockerfile" or name.startswith("Dockerfile.") or name in {"docker-compose.yml", "docker-compose.yaml"}:
            nodes.append(StaticNode(id=f"docker:{rel}", type="docker", source=rel))
        elif name in {"pyproject.toml", "package.json", "go.mod", "Cargo.toml", "requirements.txt"}:
            nodes.append(StaticNode(id=f"manifest:{rel}", type="manifest", source=rel))
    return nodes


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
    py_nodes, py_edges, py_unresolved = collect_python_graph(subject, py_roots)
    fe_nodes, fe_edges, fe_unresolved = collect_frontend_graph(subject, fe_roots)
    production = {n.id[3:] for n in py_nodes}
    test_nodes, test_edges, test_unresolved = collect_test_graph(subject, production)
    surfaces = collect_surfaces(subject)
    overlay = load_overlay(overlay_path)

    nodes: list[dict[str, Any]] = [
        {"id": n.id, "type": n.type, "source": n.source, "layer": "generated"}
        for n in [*py_nodes, *fe_nodes, *test_nodes, *surfaces]
    ]
    for item in overlay.get("nodes") or []:
        node = dict(item)
        node.setdefault("layer", "overlay")
        nodes.append(node)
    edges: list[dict[str, Any]] = [
        {"from": e.source, "to": e.target, "type": e.type, "evidence": e.evidence, "layer": "generated"}
        for e in [*py_edges, *fe_edges, *test_edges]
    ]
    for item in overlay.get("edges") or []:
        edge = dict(item)
        edge.setdefault("layer", "overlay")
        edges.append(edge)

    unresolved = _dedupe_unresolved([*py_unresolved, *fe_unresolved, *test_unresolved])
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
    overlay_count = sum(1 for n in nodes if n.get("layer") == "overlay")
    return {
        "schema_version": "1.1",
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
        "facts": {
            "unresolved_imports": unresolved,
            "unresolved_package_roots": sorted({_package_root(row["specifier"]) for row in unresolved}),
        },
        "metrics": {
            **_metrics(node_ids, edges),
            "overlay_node_count": overlay_count,
            "unresolved_import_count": len(unresolved),
            "surface_count": len(surfaces),
        },
    }


def _dedupe_unresolved(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda r: (r["specifier"], r["from"])):
        key = (row["specifier"], row["from"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
