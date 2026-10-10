"""Generated inventory Ajenda already proved: migrations, tables, egress, routes.

Ported from 1devteam/ajenda-ai scripts/validation/graph_semantic_inventory.py.
Ajenda overlay policy (RLS completeness, governed egress) stays overlay.
This module emits source-backed facts only.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_RLS_ENABLE_RE = re.compile(r"ALTER\s+TABLE\s+([A-Za-z0-9_]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.I)
_RLS_FORCE_RE = re.compile(r"ALTER\s+TABLE\s+([A-Za-z0-9_]+)\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", re.I)
_POLICY_RE = re.compile(r"CREATE\s+POLICY\s+([A-Za-z0-9_]+)\s+ON\s+([A-Za-z0-9_]+)", re.I)
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "request", "head", "options"})
_NETWORK_LIBRARIES = frozenset({"httpx", "requests", "smtplib", "aiohttp"})
_ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "websocket"})
_SKIP = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}


def _rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def _skip(path: Path) -> bool:
    return any(part in _SKIP for part in path.parts)


def _production_py(subject: Path) -> list[Path]:
    files: list[Path] = []
    for path in subject.rglob("*.py"):
        if _skip(path):
            continue
        rel = _rel(subject, path)
        parts = set(Path(rel).parts)
        if parts & {"tests", "test", "fixtures", "migrations", "alembic"}:
            continue
        files.append(path)
    return sorted(files)


def _module_for_path(subject: Path, path: Path) -> str:
    rel = path.relative_to(subject).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_strings(node: ast.AST | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_literal_string(item) for item in node.elts]
        return tuple(v for v in values if v)
    value = _literal_string(node)
    return (value,) if value else ()


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _migration_table_changes(tree: ast.Module) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = defaultdict(set)
    for item in ast.walk(tree):
        if not isinstance(item, ast.Call):
            continue
        call_name = _call_name(item.func)
        if call_name == "op.create_table" and item.args:
            table = _literal_string(item.args[0])
            if not table:
                continue
            tables.setdefault(table, set())
            for argument in item.args[1:]:
                if not isinstance(argument, ast.Call):
                    continue
                if _call_name(argument.func) not in {"sa.Column", "sqlalchemy.Column"} or not argument.args:
                    continue
                column = _literal_string(argument.args[0])
                if column:
                    tables[table].add(column)
        elif call_name == "op.add_column" and len(item.args) >= 2:
            table = _literal_string(item.args[0])
            column_call = item.args[1]
            if not table or not isinstance(column_call, ast.Call):
                continue
            if _call_name(column_call.func) not in {"sa.Column", "sqlalchemy.Column"} or not column_call.args:
                continue
            column = _literal_string(column_call.args[0])
            if column:
                tables[table].add(column)
    return dict(tables)


def _record_rls_sql(sql: str, *, enabled: set[str], forced: set[str], policies: dict[str, set[str]]) -> None:
    enabled.update(match.group(1) for match in _RLS_ENABLE_RE.finditer(sql))
    forced.update(match.group(1) for match in _RLS_FORCE_RE.finditer(sql))
    for match in _POLICY_RE.finditer(sql):
        policies[match.group(2)].add(match.group(1))


def collect_migrations(subject: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    touched: dict[str, set[str]] = defaultdict(set)
    columns: dict[str, set[str]] = defaultdict(set)
    enabled: set[str] = set()
    forced: set[str] = set()
    policies: dict[str, set[str]] = defaultdict(set)
    for root in (subject / "alembic" / "versions", subject / "migrations" / "versions"):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.py")):
            if _skip(path):
                continue
            rel = _rel(subject, path)
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text, filename=rel)
            except (OSError, SyntaxError):
                continue
            table_changes = _migration_table_changes(tree)
            migration_enabled: set[str] = set()
            migration_forced: set[str] = set()
            migration_policies: dict[str, set[str]] = defaultdict(set)
            _record_rls_sql(text, enabled=migration_enabled, forced=migration_forced, policies=migration_policies)
            enabled.update(migration_enabled)
            forced.update(migration_forced)
            for table, names in migration_policies.items():
                policies[table].update(names)
            migration_tables = set(table_changes) | migration_enabled | migration_forced | set(migration_policies)
            migration_id = f"migration:{path.stem}"
            nodes.append({"id": migration_id, "type": "migration", "source": rel, "layer": "generated"})
            for table in sorted(migration_tables):
                edges.append(
                    {
                        "from": migration_id,
                        "to": f"db:table:{table}",
                        "type": "creates_or_alters_table",
                        "evidence": rel,
                        "layer": "generated",
                    }
                )
                touched[table].add(rel)
            for table, cols in table_changes.items():
                columns[table].update(cols)
    for table in sorted(set(columns) | set(touched)):
        sources = sorted(touched.get(table, set()))
        table_source = sources[-1] if sources else None
        nodes.append(
            {
                "id": f"db:table:{table}",
                "type": "database_table",
                "label": table,
                "source": table_source,
                "layer": "generated",
                "columns": sorted(columns.get(table, set())),
                "rls_enabled": table in enabled,
                "rls_forced": table in forced,
                "rls_policies": sorted(policies.get(table, set())),
            }
        )
        if table in enabled or table in forced or policies.get(table):
            boundary_id = f"security-boundary:rls:{table}"
            nodes.append(
                {
                    "id": boundary_id,
                    "type": "security_boundary",
                    "boundary_kind": "row_level_security",
                    "source": table_source,
                    "layer": "generated",
                    "table": table,
                    "enabled": table in enabled,
                    "forced": table in forced,
                    "policies": sorted(policies.get(table, set())),
                    "detector": "migration_sql",
                }
            )
            edges.append(
                {
                    "from": f"db:table:{table}",
                    "to": boundary_id,
                    "type": "rls_enforced",
                    "evidence": table_source,
                    "detector": "migration_sql",
                    "layer": "generated",
                }
            )
    return nodes, edges


def _network_import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in tree.body:
        if isinstance(item, ast.Import):
            for alias in item.names:
                root = alias.name.split(".", 1)[0]
                if root in _NETWORK_LIBRARIES:
                    aliases[alias.asname or root] = root
        elif isinstance(item, ast.ImportFrom) and item.module:
            root = item.module.split(".", 1)[0]
            if root in _NETWORK_LIBRARIES:
                for alias in item.names:
                    aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
    return aliases


def _network_calls(tree: ast.Module) -> list[dict[str, Any]]:
    aliases = _network_import_aliases(tree)
    if not aliases:
        return []
    client_vars: set[str] = set()
    calls: list[dict[str, Any]] = []
    for item in ast.walk(tree):
        if not isinstance(item, (ast.Assign, ast.AnnAssign)):
            continue
        value = item.value
        if not isinstance(value, ast.Call):
            continue
        name = _call_name(value.func) or ""
        root_alias = name.split(".", 1)[0]
        resolved = name.replace(root_alias, aliases.get(root_alias, root_alias), 1)
        if not resolved.startswith(
            ("httpx.Client", "httpx.AsyncClient", "requests.Session", "smtplib.SMTP", "aiohttp.ClientSession")
        ):
            continue
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        client_vars.update(target.id for target in targets if isinstance(target, ast.Name))
    for item in ast.walk(tree):
        if not isinstance(item, ast.Call):
            continue
        name = _call_name(item.func) or ""
        parts = name.split(".")
        root = parts[0] if parts else ""
        resolved_root = aliases.get(root, root)
        kind: str | None = None
        if resolved_root in _NETWORK_LIBRARIES and len(parts) >= 2 and parts[-1].lower() in _HTTP_METHODS:
            kind = f"{resolved_root}.{parts[-1].lower()}"
        elif root in client_vars and len(parts) >= 2 and parts[-1].lower() in _HTTP_METHODS:
            kind = f"client.{parts[-1].lower()}"
        elif resolved_root == "smtplib" and len(parts) >= 2 and parts[-1] in {"SMTP", "SMTP_SSL"}:
            kind = f"smtplib.{parts[-1]}"
        if kind is None:
            continue
        literal_urls: list[str] = []
        arguments = [*item.args, *(keyword.value for keyword in item.keywords)]
        for argument in arguments:
            for descendant in ast.walk(argument):
                value = _literal_string(descendant)
                if value and value.startswith(("https://", "http://")):
                    literal_urls.append(value)
        hosts = sorted({h for url in literal_urls if (h := (urlparse(url).hostname or "").lower().strip())})
        calls.append({"kind": kind, "line": getattr(item, "lineno", None), "hosts": hosts})
    return sorted(calls, key=lambda item: (int(item["line"] or 0), str(item["kind"])))


def collect_egress(subject: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for path in _production_py(subject):
        rel = _rel(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError):
            continue
        calls = _network_calls(tree)
        if not calls:
            continue
        module = _module_for_path(subject, path)
        sink_id = f"egress:{module}"
        hosts = sorted({host for call in calls for host in call.get("hosts", [])})
        nodes.append(
            {
                "id": sink_id,
                "type": "network_egress_sink",
                "source": rel,
                "layer": "generated",
                "calls": calls,
                "hosts": hosts,
                "classification": "unclassified",
                "start_line": int(calls[0]["line"] or 1),
                "end_line": int(calls[-1]["line"] or calls[0]["line"] or 1),
                "detector": "python_ast",
            }
        )
        edges.append(
            {
                "from": f"py:{module}",
                "to": sink_id,
                "type": "direct_network_egress",
                "evidence": rel,
                "start_line": int(calls[0]["line"] or 1),
                "end_line": int(calls[-1]["line"] or calls[0]["line"] or 1),
                "detector": "python_ast",
                "layer": "generated",
            }
        )
    return nodes, edges


def collect_routes(subject: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect distinct route declarations and only source-proven runtime composition."""

    declarations: list[dict[str, Any]] = []
    trees: dict[str, tuple[str, ast.Module]] = {}
    imports: dict[tuple[str, str], tuple[str, str]] = {}
    imported_modules: dict[tuple[str, str], str] = {}
    router_objects: dict[tuple[str, str, str], dict[str, Any]] = {}
    function_results: dict[tuple[str, str], tuple[str, str, str]] = {}
    include_edges: list[dict[str, Any]] = []

    def join_path(*parts: str) -> str:
        cleaned = [part.strip("/") for part in parts if part and part != "/"]
        return "/" + "/".join(cleaned) if cleaned else "/"

    def add_route(
        method: str,
        path_lit: str,
        rel: str,
        module: str | None,
        handler: str | None = None,
        *,
        owner: str | None = None,
        scope: str = "module",
        start_line: int,
        end_line: int,
        detector: str,
    ) -> None:
        declarations.append(
            {
                "method": method.upper(),
                "path": path_lit,
                "source": rel,
                "module": module,
                "handler": handler,
                "router_owner": owner,
                "scope": scope,
                "start_line": start_line,
                "end_line": end_line,
                "detector": detector,
            }
        )

    def imported_module_for(module: str, source_path: Path, item: ast.ImportFrom) -> str | None:
        if item.level == 0:
            return item.module
        package = module.split(".") if source_path.name == "__init__.py" else module.split(".")[:-1]
        ascend = item.level - 1
        if ascend > len(package):
            return None
        base = package[: len(package) - ascend]
        if item.module:
            base.extend(item.module.split("."))
        return ".".join(base)

    production = _production_py(subject)
    path_by_module: dict[str, Path] = {}
    for source_path in production:
        rel = _rel(subject, source_path)
        module = _module_for_path(subject, source_path)
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError):
            continue
        trees[module] = (rel, tree)
        path_by_module[module] = source_path
        for item in tree.body:
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imported_modules[(module, alias.asname or alias.name.split(".", 1)[0])] = alias.name
            elif isinstance(item, ast.ImportFrom):
                imported_module = imported_module_for(module, source_path, item)
                if not imported_module:
                    continue
                for alias in item.names:
                    imports[(module, alias.asname or alias.name)] = (imported_module, alias.name)

    def scope_bodies(tree: ast.Module) -> list[tuple[str, list[ast.stmt]]]:
        result: list[tuple[str, list[ast.stmt]]] = [("module", tree.body)]
        result.extend(
            (item.name, item.body)
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        return result

    def assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        return names[0] if len(names) == 1 else None

    # First pass: explicit router/application objects.
    for module, (rel, tree) in trees.items():
        for scope, body in scope_bodies(tree):
            for statement in body:
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                value = statement.value
                name = assigned_name(statement)
                if not name or not isinstance(value, ast.Call):
                    continue
                constructor = (_call_name(value.func) or "").rsplit(".", 1)[-1]
                if constructor not in {"APIRouter", "FastAPI"}:
                    continue
                prefix = _literal_string(_keyword(value, "prefix")) or ""
                router_objects[(module, scope, name)] = {
                    "module": module,
                    "scope": scope,
                    "name": name,
                    "prefix": prefix,
                    "kind": "application" if constructor == "FastAPI" else "router",
                    "source": rel,
                    "line": statement.lineno,
                }

    # Second pass: functions that explicitly return one of those router objects.
    for module, (_rel_path, tree) in trees.items():
        for item in tree.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            returned = [
                child.value.id
                for child in ast.walk(item)
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Name)
            ]
            keys = {
                (module, item.name, name)
                for name in returned
                if (module, item.name, name) in router_objects
            }
            if len(keys) == 1:
                function_results[(module, item.name)] = next(iter(keys))

    def resolve_router_expr(module: str, scope: str, node: ast.AST) -> tuple[str, str, str] | None:
        if isinstance(node, ast.Name):
            local = (module, scope, node.id)
            if local in router_objects:
                return local
            module_level = (module, "module", node.id)
            if module_level in router_objects:
                return module_level
            imported = imports.get((module, node.id))
            if imported:
                target_module, target_name = imported
                target_router = (target_module, "module", target_name)
                if target_router in router_objects:
                    return target_router
                return function_results.get((target_module, target_name))
            return function_results.get((module, node.id))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            imported_module = imported_modules.get((module, node.value.id))
            if imported_module:
                target = (imported_module, "module", node.attr)
                if target in router_objects:
                    return target
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                imported = imports.get((module, node.func.id))
                if imported:
                    return function_results.get(imported)
                return function_results.get((module, node.func.id))
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                imported_module = imported_modules.get((module, node.func.value.id))
                if imported_module:
                    return function_results.get((imported_module, node.func.attr))
        return None

    # Third pass: route declarations plus explicit router composition.
    for module, (rel, tree) in trees.items():
        for scope, body in scope_bodies(tree):
            for statement in body:
                for item in ast.walk(statement):
                    if isinstance(item, ast.Call):
                        name = (_call_name(item.func) or "").rsplit(".", 1)[-1]
                        if name in {"path", "re_path", "url"} and item.args:
                            path_lit = _literal_string(item.args[0])
                            if path_lit:
                                add_route(
                                    "ANY",
                                    path_lit,
                                    rel,
                                    module,
                                    start_line=item.lineno,
                                    end_line=getattr(item, "end_lineno", item.lineno),
                                    detector="python_ast",
                                    scope=scope,
                                )
                        if (
                            isinstance(item.func, ast.Attribute)
                            and item.func.attr in {"include_router", "include", "mount"}
                            and item.args
                        ):
                            parent = resolve_router_expr(module, scope, item.func.value)
                            child = resolve_router_expr(module, scope, item.args[0])
                            if parent and child:
                                include_edges.append(
                                    {
                                        "parent": parent,
                                        "child": child,
                                        "prefix": _literal_string(_keyword(item, "prefix")) or "",
                                        "source": rel,
                                        "line": item.lineno,
                                    }
                                )
                    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    handler_scope = scope
                    for decorator in item.decorator_list:
                        if not isinstance(decorator, ast.Call):
                            continue
                        name = (_call_name(decorator.func) or "").lower()
                        last = name.rsplit(".", 1)[-1]
                        path_lit = _literal_string(decorator.args[0]) if decorator.args else None
                        owner = name.rsplit(".", 1)[0] if "." in name else ""
                        owner_name = owner.rsplit(".", 1)[-1] if owner else None
                        if last == "route" and path_lit:
                            methods = _literal_strings(_keyword(decorator, "methods")) or ("GET",)
                            for method in methods:
                                add_route(
                                    method,
                                    path_lit,
                                    rel,
                                    module,
                                    item.name,
                                    owner=owner_name,
                                    scope=handler_scope,
                                    start_line=decorator.lineno,
                                    end_line=getattr(item, "end_lineno", item.lineno),
                                    detector="python_ast",
                                )
                            continue
                        if last not in _ROUTE_METHODS or not path_lit:
                            continue
                        if not owner or not path_lit.startswith("/"):
                            continue
                        if owner in {"mock", "unittest.mock"} or owner.endswith(".mock"):
                            continue
                        add_route(
                            last,
                            path_lit,
                            rel,
                            module,
                            item.name,
                            owner=owner_name,
                            scope=handler_scope,
                            start_line=decorator.lineno,
                            end_line=getattr(item, "end_lineno", item.lineno),
                            detector="python_ast",
                        )

    js_re = re.compile(
        r"\b(?:app|router|api)\.(get|post|put|patch|delete|all)\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*([A-Za-z_$][\w$]*))?",
        re.I,
    )
    for path in subject.rglob("*"):
        if _skip(path) or path.suffix.lower() not in {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}:
            continue
        rel = _rel(subject, path)
        parts = set(Path(rel).parts)
        if parts & {"tests", "test", "__tests__", "node_modules"} or re.search(r"\.(?:test|spec)\.[^.]+$", rel, re.I):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in js_re.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            add_route(
                match.group(1),
                match.group(2),
                rel,
                f"js:{rel}",
                match.group(3),
                owner="router",
                start_line=line,
                end_line=line,
                detector="javascript_route_pattern",
            )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    declaration_to_router: dict[str, tuple[str, str, str]] = {}

    for declaration in declarations:
        method = str(declaration["method"])
        path_lit = str(declaration["path"])
        rel = str(declaration["source"])
        module = declaration["module"]
        handler = str(declaration["handler"] or "")
        owner = str(declaration.get("router_owner") or "")
        scope = str(declaration.get("scope") or "module")
        line = int(declaration["start_line"])
        declaration_owner = str(module or rel)
        route_id = f"route-declaration:{declaration_owner}:{method}:{path_lit}@L{line}"
        nodes.append(
            {
                "id": route_id,
                "type": "http_route",
                "route_identity": "declaration",
                "source": rel,
                "layer": "generated",
                "method": method,
                "path": path_lit,
                "handler": declaration["handler"],
                "router_owner": owner or None,
                "start_line": line,
                "end_line": declaration["end_line"],
                "detector": declaration["detector"],
            }
        )
        if module:
            edges.append(
                {
                    "from": module if str(module).startswith("js:") else f"py:{module}",
                    "to": route_id,
                    "type": "declares_route",
                    "evidence": rel,
                    "start_line": line,
                    "end_line": declaration["end_line"],
                    "symbol": declaration["handler"],
                    "detector": declaration["detector"],
                    "layer": "generated",
                }
            )
        if module and owner:
            router_key = resolve_router_expr(str(module), scope, ast.Name(id=owner))
            if router_key:
                declaration_to_router[route_id] = router_key

    includes_by_parent: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    children: set[tuple[str, str, str]] = set()
    for item in include_edges:
        includes_by_parent[item["parent"]].append(item)
        children.add(item["child"])

    declaration_ids_by_router: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    node_by_id = {str(node["id"]): node for node in nodes}
    for route_id, router_key in declaration_to_router.items():
        declaration_ids_by_router[router_key].append(route_id)

    runtime_sources: dict[str, set[str]] = defaultdict(set)
    runtime_nodes: dict[str, dict[str, Any]] = {}
    composition_edges: list[dict[str, Any]] = []

    roots = [
        key
        for key, value in router_objects.items()
        if value["kind"] == "application" and key not in children
    ]

    def walk_router(
        router_key: tuple[str, str, str],
        accumulated_prefix: str,
        trail: tuple[tuple[str, str, str], ...],
    ) -> None:
        if router_key in trail:
            return
        router = router_objects[router_key]
        current_prefix = join_path(accumulated_prefix, str(router.get("prefix") or ""))
        for route_id in declaration_ids_by_router.get(router_key, []):
            declaration_node = node_by_id[route_id]
            full_path = join_path(current_prefix, str(declaration_node["path"]))
            runtime_id = f"runtime-route:{declaration_node['method']}:{full_path}"
            runtime_sources[runtime_id].add(str(declaration_node.get("source") or ""))
            runtime_nodes.setdefault(
                runtime_id,
                {
                    "id": runtime_id,
                    "type": "runtime_route",
                    "route_identity": "runtime-composed",
                    "source": None,
                    "layer": "generated",
                    "method": declaration_node["method"],
                    "path": full_path,
                    "composition_proven": True,
                    "detector": "python_ast_route_composition",
                },
            )
            composition_edges.append(
                {
                    "from": route_id,
                    "to": runtime_id,
                    "type": "composes_to",
                    "evidence": str(declaration_node.get("source") or ""),
                    "start_line": declaration_node.get("start_line"),
                    "end_line": declaration_node.get("end_line"),
                    "symbol": declaration_node.get("handler"),
                    "detector": "python_ast_route_composition",
                    "layer": "generated",
                }
            )
        for include in includes_by_parent.get(router_key, []):
            child = include["child"]
            walk_router(
                child,
                join_path(current_prefix, str(include.get("prefix") or "")),
                (*trail, router_key),
            )

    for root in roots:
        walk_router(root, "", ())

    for runtime_id, node in runtime_nodes.items():
        sources = sorted(source for source in runtime_sources[runtime_id] if source)
        node["sources"] = sources
        if len(sources) == 1:
            node["source"] = sources[0]
        nodes.append(node)
    edges.extend(composition_edges)

    return sorted(nodes, key=lambda node: str(node["id"])), sorted(
        edges,
        key=lambda edge: (str(edge["from"]), str(edge["to"]), str(edge["type"])),
    )



def collect_orm_tables(subject: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _production_py(subject):
        rel = _rel(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError):
            continue
        module = _module_for_path(subject, path)
        for item in tree.body:
            if not isinstance(item, ast.ClassDef):
                continue
            table = None
            bases = []
            for base in item.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(base.attr)
            django = "Model" in bases
            for stmt in item.body:
                if isinstance(stmt, ast.Assign):
                    names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                    if "__tablename__" in names:
                        table = _literal_string(stmt.value)
            if django and not table:
                table = item.name.lower()
            if not table:
                continue
            tid = f"db:table:{table}"
            if tid not in seen:
                seen.add(tid)
                nodes.append(
                    {
                        "id": tid,
                        "type": "database_table",
                        "label": table,
                        "source": rel,
                        "layer": "generated",
                        "orm": "sqlalchemy" if not django else "django",
                        "start_line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "detector": "python_ast",
                    }
                )
            edges.append(
                {
                    "from": f"py:{module}",
                    "to": tid,
                    "type": "defines_table",
                    "evidence": rel,
                    "start_line": item.lineno,
                    "end_line": getattr(item, "end_lineno", item.lineno),
                    "symbol": table,
                    "detector": "python_ast",
                    "layer": "generated",
                }
            )
    return nodes, edges


_CONTRACT_BASES = frozenset({"BaseModel", "Protocol", "TypedDict", "Enum"})
_TS_INTERFACE_RE = re.compile(r"export\s+(?:interface|type)\s+([A-Za-z_][A-Za-z0-9_]*)")


def collect_contracts(subject: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for path in _production_py(subject):
        rel = _rel(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError):
            continue
        module = _module_for_path(subject, path)
        for item in tree.body:
            is_dataclass = any(
                (isinstance(d, ast.Name) and d.id == "dataclass")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                for d in getattr(item, "decorator_list", [])
            )
            bases: list[str] = []
            if isinstance(item, ast.ClassDef):
                for base in item.bases:
                    name = _call_name(base) if not isinstance(base, ast.Name) else base.id
                    if isinstance(base, ast.Attribute):
                        name = base.attr
                    elif isinstance(base, ast.Name):
                        name = base.id
                    else:
                        name = None
                    if name:
                        bases.append(name)
            if not isinstance(item, ast.ClassDef):
                continue
            if not is_dataclass and not (set(bases) & _CONTRACT_BASES):
                continue
            cid = f"contract:{module}:{item.name}"
            nodes.append(
                {
                    "id": cid,
                    "type": "contract",
                    "source": rel,
                    "layer": "generated",
                    "name": item.name,
                    "bases": bases,
                    "kind": "dataclass" if is_dataclass else "model",
                    "start_line": item.lineno,
                    "end_line": getattr(item, "end_lineno", item.lineno),
                    "detector": "python_ast",
                }
            )
            edges.append(
                {
                    "from": f"py:{module}",
                    "to": cid,
                    "type": "defines_contract",
                    "evidence": rel,
                    "start_line": item.lineno,
                    "end_line": getattr(item, "end_lineno", item.lineno),
                    "symbol": item.name,
                    "detector": "python_ast",
                    "layer": "generated",
                }
            )
    for path in subject.rglob("*"):
        if _skip(path) or path.suffix not in {".ts", ".tsx"}:
            continue
        rel = _rel(subject, path)
        parts = set(Path(rel).parts)
        if parts & {"tests", "test", "__tests__", "node_modules"} or re.search(r"\.(?:test|spec)\.[^.]+$", rel, re.I):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _TS_INTERFACE_RE.finditer(text):
            name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            cid = f"contract:{rel}:{name}"
            nodes.append(
                {
                    "id": cid,
                    "type": "contract",
                    "source": rel,
                    "layer": "generated",
                    "name": name,
                    "kind": "typescript",
                    "start_line": line,
                    "end_line": line,
                    "detector": "typescript_declaration_pattern",
                }
            )
            edges.append(
                {
                    "from": f"js:{rel}",
                    "to": cid,
                    "type": "defines_contract",
                    "evidence": rel,
                    "start_line": line,
                    "end_line": line,
                    "symbol": name,
                    "detector": "typescript_declaration_pattern",
                    "layer": "generated",
                }
            )
    return nodes, edges


def collect_semantic(subject: Path) -> dict[str, Any]:
    mig_nodes, mig_edges = collect_migrations(subject)
    orm_nodes, orm_edges = collect_orm_tables(subject)
    known_tables = {n["id"] for n in mig_nodes if n.get("type") == "database_table"}
    orm_nodes = [n for n in orm_nodes if n["id"] not in known_tables]
    egress_nodes, egress_edges = collect_egress(subject)
    route_nodes, route_edges = collect_routes(subject)
    contract_nodes, contract_edges = collect_contracts(subject)
    return {
        "nodes": [*mig_nodes, *orm_nodes, *egress_nodes, *route_nodes, *contract_nodes],
        "edges": [*mig_edges, *orm_edges, *egress_edges, *route_edges, *contract_edges],
    }
