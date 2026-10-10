"""Build the canonical, source-backed G.R.A.F.T.+ graph."""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

from graft_plus.adapters import collect_javascript_graph, collect_shell_graph
from graft_plus.architecture import collect_architecture_topology
from graft_plus.boundaries import collect_relationship_boundaries
from graft_plus.configuration import collect_configuration_graph
from graft_plus.contracts import collect_contract_file_graph
from graft_plus.evidence import attach_evidence_anchors
from graft_plus.functions import collect_function_graph
from graft_plus.graph_types import StaticEdge, StaticNode
from graft_plus.inventory import collect_package_topology, inventory_nodes, relevant_files
from graft_plus.languages import collect_additional_language_graph
from graft_plus.runtime import is_runtime
from graft_plus.runtime_declarations import collect_runtime_declarations

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


def load_overlay(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"schema_version": "1.0", "nodes": [], "edges": [], "invariants": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("overlay root must be an object")
    return payload


def discover_overlay(subject: Path, explicit: Path | None) -> Path | None:
    """Use an explicit overlay or a repository-owned conventional reviewed overlay."""

    if explicit is not None:
        return explicit
    for relative in (
        "docs/contracts/dependency-graph.overlay.v1.json",
        ".graft/dependency-graph.overlay.v1.json",
        ".graft/overlay.json",
    ):
        candidate = subject / relative
        if candidate.is_file():
            return candidate
    return None


def _aggregate_occurrence_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve repeated evidence without serializing duplicate topology edges."""

    aggregate_types = {"calls_function", "tests_function", "injects_dependency"}
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for edge in edges:
        edge_type = str(edge.get("type") or "")
        if edge_type not in aggregate_types:
            passthrough.append(edge)
            continue
        key = (
            str(edge.get("from") or ""),
            str(edge.get("to") or ""),
            edge_type,
            str(edge.get("layer") or ""),
        )
        grouped.setdefault(key, []).append(edge)

    aggregated: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        first = dict(rows[0])
        observations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            observation = {
                field: row.get(field)
                for field in ("evidence", "start_line", "end_line", "symbol", "detector")
                if row.get(field) is not None
            }
            token = json.dumps(observation, sort_keys=True, separators=(",", ":"))
            if token in seen:
                continue
            seen.add(token)
            observations.append(observation)
        observations.sort(
            key=lambda item: (
                str(item.get("evidence") or ""),
                int(item.get("start_line") or 0),
                int(item.get("end_line") or 0),
                str(item.get("symbol") or ""),
            )
        )
        if observations:
            first.update(observations[0])
        first["occurrences"] = len(observations) or len(rows)
        if len(observations) > 1:
            first["observations"] = observations
        aggregated.append(first)
    return [*passthrough, *aggregated]


def build_graph(*, subject: Path, overlay_path: Path | None = None) -> dict[str, Any]:
    subject = subject.resolve()
    requested_overlay_path = overlay_path
    overlay_path = discover_overlay(subject, overlay_path)
    py_roots = discover_python_roots(subject)
    py_nodes, py_edges, py_unresolved = collect_python_graph(subject, py_roots)
    production = {n.id[3:] for n in py_nodes}
    test_nodes, test_edges, test_unresolved = collect_test_graph(subject, production)
    js_nodes, js_edges, js_unresolved = collect_javascript_graph(subject)
    python_by_source = {node.source: node.id for node in py_nodes}
    shell_nodes, shell_edges, shell_unresolved = collect_shell_graph(subject, python_by_source)
    language_nodes, language_edges, language_unresolved = collect_additional_language_graph(subject)
    surfaces = collect_surfaces(subject)
    overlay = load_overlay(overlay_path)
    from graft_plus.semantic import collect_semantic

    semantic = collect_semantic(subject)

    nodes: list[dict[str, Any]] = [
        {"id": n.id, "type": n.type, "source": n.source, "layer": "generated"}
        for n in [*py_nodes, *test_nodes, *js_nodes, *shell_nodes, *language_nodes, *surfaces]
    ]
    nodes.extend(semantic["nodes"])
    function_nodes, function_edges = collect_function_graph(subject, overlay, python_by_source)
    nodes.extend(function_nodes)
    runtime_declarations = collect_runtime_declarations(subject, function_nodes)
    nodes.extend(runtime_declarations["nodes"])
    for item in overlay.get("nodes") or []:
        node = dict(item)
        node.setdefault("layer", "overlay")
        nodes.append(node)
    edges: list[dict[str, Any]] = [
        {"from": e.source, "to": e.target, "type": e.type, "evidence": e.evidence, "layer": "generated"}
        for e in [*py_edges, *test_edges, *js_edges, *shell_edges, *language_edges]
    ]
    edges.extend(e for e in semantic["edges"] if e.get("from") and e.get("to"))
    edges.extend(function_edges)
    edges.extend(runtime_declarations["edges"])
    route_handlers: dict[tuple[str, str], list[str]] = {}
    for node in function_nodes:
        if not node.get("route_handler"):
            continue
        key = (str(node.get("source") or ""), str(node.get("name") or ""))
        route_handlers.setdefault(key, []).append(str(node["id"]))
    for route in semantic["nodes"]:
        if route.get("type") != "http_route" or not route.get("handler"):
            continue
        source = str(route.get("source") or "")
        candidates = route_handlers.get((source, str(route["handler"])), [])
        if len(candidates) != 1:
            continue
        edges.append(
            {
                "from": route["id"],
                "to": candidates[0],
                "type": "handled_by",
                "evidence": source,
                "start_line": route.get("start_line"),
                "end_line": route.get("end_line"),
                "symbol": route["handler"],
                "detector": route.get("detector") or "python_ast",
                "layer": "generated",
            }
        )
    for item in overlay.get("edges") or []:
        edge = dict(item)
        edge.setdefault("layer", "overlay")
        edges.append(edge)

    source_node_ids = {
        node.source: node.id
        for node in [*py_nodes, *test_nodes, *js_nodes, *shell_nodes, *language_nodes, *surfaces]
    }
    package_nodes, package_edges = collect_package_topology(subject, source_node_ids)
    nodes.extend(package_nodes)
    edges.extend(package_edges)
    contract_file_nodes, contract_file_edges, contract_file_facts = collect_contract_file_graph(
        subject, source_node_ids
    )
    nodes.extend(contract_file_nodes)
    edges.extend(contract_file_edges)
    configuration_nodes, configuration_edges, configuration_facts = collect_configuration_graph(
        subject, source_node_ids
    )
    nodes.extend(configuration_nodes)
    edges.extend(configuration_edges)
    architecture_nodes, architecture_edges, architecture_facts, architecture_annotations = collect_architecture_topology(
        subject, nodes
    )
    for node in nodes:
        annotation = architecture_annotations.get(str(node.get("id") or ""))
        if annotation:
            node.update(annotation)
    nodes.extend(architecture_nodes)
    edges.extend(architecture_edges)
    mapped_sources = {
        str(node["source"])
        for node in nodes
        if isinstance(node.get("source"), str) and node.get("source")
    }
    fallback_nodes, inventory_facts = inventory_nodes(subject, mapped_sources=mapped_sources)
    nodes.extend(fallback_nodes)
    boundary_facts = collect_relationship_boundaries(subject)

    unresolved = _dedupe_unresolved(
        [*py_unresolved, *test_unresolved, *js_unresolved, *shell_unresolved, *language_unresolved]
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
    edges = _aggregate_occurrence_edges(edges)
    attach_evidence_anchors(subject, nodes, edges)
    evidence_precision_counts = {
        "nodes": dict(
            sorted(Counter(str(node.get("evidence_anchor", {}).get("precision") or "none") for node in nodes).items())
        ),
        "edges": dict(
            sorted(Counter(str(edge.get("evidence_anchor", {}).get("precision") or "none") for edge in edges).items())
        ),
    }
    edge_by_key: dict[str, dict[str, Any]] = {}
    for edge in edges:
        key = json.dumps(edge, sort_keys=True, separators=(",", ":"))
        edge_by_key[key] = edge
    edges = list(edge_by_key.values())
    overlay_rel = None
    if overlay_path and overlay_path.exists():
        try:
            overlay_rel = str(overlay_path.resolve().relative_to(subject))
        except ValueError:
            overlay_rel = str(overlay_path)
    return {
        "schema_version": "1.14",
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "role": "fact-substrate",
        "implementsPlan": False,
        "grants_execution_authority": False,
        "semantic_provenance": {
            "semantic_authority": "1devteam/graft_plus",
            "canonical_engine": "python-universal-shell",
            "canonical_schema_version": "1.14",
            "website_execution_authority": "1devteam/1devteam-web",
            "website_synchronization_mode": "github-reviewed-manual-port",
            "website_runtime_dependency": "none",
            "overlay_mode": (
                "explicit"
                if requested_overlay_path is not None
                else "auto-discovered"
                if overlay_path is not None
                else "none"
            ),
        },
        "generated_from": {
            "python_roots": [str(p.relative_to(subject)) if p != subject else "." for p in py_roots],
            "adapters": [
                "python",
                "javascript-typescript",
                "shell-bats",
                "go",
                "rust",
                "ruby",
                "php",
                "c-cpp",
                "java-kotlin-scala",
                "csharp",
                "lua",
                "elixir",
                "swift",
                "package-manifests",
                "relationship-boundary-ledger",
                "contract-declarations",
                "configuration-deployment",
                "subsystem-hierarchy",
                "build-system-topology",
                "source-provenance",
                "cross-language-subsystem-joins",
                "governance-boundaries",
                "evidence-anchors",
                "route-declaration-composition",
                "dependency-provider-topology",
                "runtime-declaration-contracts",
            ],
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
            **boundary_facts,
            **contract_file_facts,
            **configuration_facts,
            **architecture_facts,
            **runtime_declarations["facts"],
            "evidence_precision_counts": evidence_precision_counts,
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
