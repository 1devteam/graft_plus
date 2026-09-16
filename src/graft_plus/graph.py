"""Build the canonical, source-backed G.R.A.F.T.+ graph."""

from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from graft_plus.adapters import collect_javascript_graph, collect_shell_graph
from graft_plus.functions import collect_function_graph
from graft_plus.graph_types import StaticEdge, StaticNode
from graft_plus.inventory import collect_package_topology, inventory_nodes, relevant_files
from graft_plus.runtime import is_runtime

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache"}


def _rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def _runtime(specifier: str) -> bool:
    return is_runtime(specifier)


def _package_root(specifier: str) -> str:
    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split(".")[0].split("/")[0]


def _skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def discover_python_roots(subject: Path) -> list[Path]:
    return [subject] if any(path.is_file() and not _skip(path) for path in subject.rglob("*.py")) else []


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
            source = _rel(subject, path)
            parts = set(Path(source).parts)
            if parts & {"tests", "test", "fixtures", "migrations", "alembic"}:
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
                if not name:
                    continue
                target = _best_target(name, modules)
                if target and target != module:
                    imported.add(target)
                elif not target and not _runtime(name):
                    unresolved.append({"specifier": name, "from": rel})
        for target in imported:
            edges.add(StaticEdge(source=f"py:{module}", target=f"py:{target}", type="imports", evidence=rel))
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type)), unresolved


def collect_test_graph(subject: Path, production_modules: set[str]) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    nodes: list[StaticNode] = []
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path in subject.rglob("*.py"):
        rel = _rel(subject, path)
        parts = Path(rel).parts
        if _skip(path) or "fixtures" in parts or not ({"tests", "test"} & set(parts)):
            continue
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
                if not name:
                    continue
                target = _best_target(name, production_modules)
                if target:
                    edges.add(StaticEdge(source=node_id, target=f"py:{target}", type="tests", evidence=rel))
                elif not _runtime(name):
                    unresolved.append({"specifier": name, "from": rel})
    return nodes, sorted(edges, key=lambda e: (e.source, e.target, e.type)), unresolved


def collect_surfaces(subject: Path) -> list[StaticNode]:
    nodes: list[StaticNode] = []
    for path in relevant_files(subject):
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
        "top_production_fan_in": [
            item for item in ranked(fan_in) if not str(item["node"]).startswith("test:")
        ],
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
    py_nodes, py_edges, py_unresolved = collect_python_graph(subject, py_roots)
    production = {n.id[3:] for n in py_nodes}
    test_nodes, test_edges, test_unresolved = collect_test_graph(subject, production)
    js_nodes, js_edges, js_unresolved = collect_javascript_graph(subject)
    python_by_source = {node.source: node.id for node in py_nodes}
    shell_nodes, shell_edges, shell_unresolved = collect_shell_graph(subject, python_by_source)
    surfaces = collect_surfaces(subject)
    overlay = load_overlay(overlay_path)
    from graft_plus.semantic import collect_semantic

    semantic = collect_semantic(subject)

    nodes: list[dict[str, Any]] = [
        {"id": n.id, "type": n.type, "source": n.source, "layer": "generated"}
        for n in [*py_nodes, *test_nodes, *js_nodes, *shell_nodes, *surfaces]
    ]
    nodes.extend(semantic["nodes"])
    function_nodes, function_edges = collect_function_graph(subject, overlay, python_by_source)
    nodes.extend(function_nodes)
    for item in overlay.get("nodes") or []:
        node = dict(item)
        node.setdefault("layer", "overlay")
        nodes.append(node)
    edges: list[dict[str, Any]] = [
        {"from": e.source, "to": e.target, "type": e.type, "evidence": e.evidence, "layer": "generated"}
        for e in [*py_edges, *test_edges, *js_edges, *shell_edges]
    ]
    edges.extend(e for e in semantic["edges"] if e.get("from") and e.get("to"))
    edges.extend(function_edges)
    for item in overlay.get("edges") or []:
        edge = dict(item)
        edge.setdefault("layer", "overlay")
        edges.append(edge)

    source_node_ids = {
        node.source: node.id
        for node in [*py_nodes, *test_nodes, *js_nodes, *shell_nodes, *surfaces]
    }
    package_nodes, package_edges = collect_package_topology(subject, source_node_ids)
    nodes.extend(package_nodes)
    edges.extend(package_edges)
    mapped_sources = {
        str(node["source"])
        for node in nodes
        if isinstance(node.get("source"), str) and node.get("source")
    }
    fallback_nodes, inventory_facts = inventory_nodes(subject, mapped_sources=mapped_sources)
    nodes.extend(fallback_nodes)

    unresolved = _dedupe_unresolved(
        [*py_unresolved, *test_unresolved, *js_unresolved, *shell_unresolved]
    )
    dependency_ids = {
        str(node.get("name")): str(node["id"])
        for node in package_nodes
        if node.get("type") == "external_dependency" and node.get("name")
    }
    declared_external_imports: list[dict[str, str]] = []
    still_unresolved: list[dict[str, str]] = []
    for row in unresolved:
        package_name = _package_root(row["specifier"])
        target = dependency_ids.get(package_name)
        source_id = source_node_ids.get(row["from"])
        if target and source_id:
            edges.append(
                {
                    "from": source_id,
                    "to": target,
                    "type": "imports_package",
                    "evidence": row["from"],
                    "layer": "generated",
                }
            )
            declared_external_imports.append({**row, "package": package_name})
        else:
            still_unresolved.append(row)
    unresolved = still_unresolved
    ids = [str(n["id"]) for n in nodes]
    dupes = sorted(i for i, c in Counter(ids).items() if c > 1)
    if dupes:
        raise ValueError(f"duplicate nodes: {', '.join(dupes)}")
    known = set(ids)
    missing = sorted(
        {
            str(endpoint)
            for edge in edges
            for endpoint in (edge.get("from"), edge.get("to"))
            if str(endpoint) not in known
        }
    )
    if missing:
        raise ValueError(f"undefined edge endpoints: {', '.join(missing)}")
    edge_by_key: dict[str, dict[str, Any]] = {}
    for edge in edges:
        key = json.dumps(edge, sort_keys=True, separators=(",", ":"))
        edge_by_key[key] = edge
    edges = list(edge_by_key.values())
    node_ids = sorted(known)
    overlay_rel = None
    if overlay_path and overlay_path.exists():
        try:
            overlay_rel = str(overlay_path.resolve().relative_to(subject))
        except ValueError:
            overlay_rel = str(overlay_path)
    overlay_count = sum(1 for n in nodes if n.get("layer") == "overlay")
    return {
        "schema_version": "1.3",
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "role": "fact-substrate",
        "implementsPlan": False,
        "grants_execution_authority": False,
        "generated_from": {
            "python_roots": [str(p.relative_to(subject)) if p != subject else "." for p in py_roots],
            "adapters": ["python", "javascript-typescript", "shell-bats", "package-manifests"],
            "function_roots": overlay.get("function_roots") or [],
            "overlay": overlay_rel,
        },
        "nodes": sorted(nodes, key=lambda n: str(n["id"])),
        "edges": sorted(edges, key=lambda e: (str(e["from"]), str(e["to"]), str(e["type"]))),
        "invariants": overlay.get("invariants") or [],
        "facts": {
            "unresolved_imports": unresolved,
            "unresolved_package_roots": sorted({_package_root(row["specifier"]) for row in unresolved}),
            "declared_external_imports": declared_external_imports,
            **inventory_facts,
        },
        "metrics": {
            **_metrics(node_ids, edges),
            "overlay_node_count": overlay_count,
            "unresolved_import_count": len(unresolved),
            "surface_count": len(surfaces),
            "inventory_file_count": inventory_facts["file_count"],
            "relationship_parsed_file_count": inventory_facts["relationship_parsed_file_count"],
            "relationship_unparsed_file_count": inventory_facts["relationship_unparsed_file_count"],
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
