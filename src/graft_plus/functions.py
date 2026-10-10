"""Participation-based, source-backed Python callable topology.

Definitions are collected repository-wide, but only callables that participate
in a proven call, test reference, route decoration, exact callable binding,
entrypoint convention, or an overlay-selected root are emitted. This keeps
responsibility topology visible without turning the artifact into a source dump.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graft_plus.inventory import rel, skipped

_BINDING_HANDLER_KEYWORDS = ("handler", "callback", "func", "function", "callable")
_BINDING_IDENTITY_KEYWORDS = ("name", "id", "key", "action", "event")


@dataclass(frozen=True, slots=True)
class CallableDef:
    node: ast.FunctionDef | ast.AsyncFunctionDef
    module: str
    source: str
    qualified_name: str
    owner_class: str | None = None
    enclosing_function: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.module, self.qualified_name

    @property
    def id(self) -> str:
        return f"fn:{self.module}:{self.qualified_name}"


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


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _declared_value(node: ast.AST) -> Any:
    """Return source-backed declaration metadata without interpreting it."""

    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_declared_value(item) for item in node.elts]
        if all(value is not None for value in values):
            return values
        return None
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key, value in zip(node.keys, node.values, strict=False):
            key_value = _literal_string(key)
            declared = _declared_value(value)
            if key_value is None or declared is None:
                return None
            result[key_value] = declared
        return result
    name = _call_name(node)
    if name:
        return {"symbol": name}
    if isinstance(node, ast.Call):
        call_name = _call_name(node.func)
        if call_name:
            payload: dict[str, Any] = {"call": call_name}
            keyword_values: dict[str, Any] = {}
            for keyword in node.keywords:
                if not keyword.arg:
                    continue
                declared = _declared_value(keyword.value)
                if declared is not None:
                    keyword_values[keyword.arg] = declared
            if keyword_values:
                payload["keywords"] = keyword_values
            return payload
    try:
        rendered = ast.unparse(node).strip()
    except (AttributeError, ValueError):
        return None
    return {"expression": rendered[:240]} if rendered else None


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


def _nested_callables(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module: str,
    source: str,
    prefix: str,
    owner_class: str | None = None,
) -> list[CallableDef]:
    result: list[CallableDef] = []
    for child in function.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        qualified = f"{prefix}.{child.name}"
        result.append(
            CallableDef(
                child,
                module,
                source,
                qualified,
                owner_class=owner_class,
                enclosing_function=prefix,
            )
        )
        result.extend(
            _nested_callables(
                child,
                module=module,
                source=source,
                prefix=qualified,
                owner_class=owner_class,
            )
        )
    return result


def _callable_definitions(tree: ast.Module, *, module: str, source: str) -> list[CallableDef]:
    result: list[CallableDef] = []
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(CallableDef(item, module, source, item.name))
            result.extend(
                _nested_callables(
                    item,
                    module=module,
                    source=source,
                    prefix=item.name,
                )
            )
        elif isinstance(item, ast.ClassDef):
            for child in item.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                qualified = f"{item.name}.{child.name}"
                result.append(
                    CallableDef(
                        child,
                        module,
                        source,
                        qualified,
                        owner_class=item.name,
                    )
                )
                result.extend(
                    _nested_callables(
                        child,
                        module=module,
                        source=source,
                        prefix=qualified,
                        owner_class=item.name,
                    )
                )
    return result


def _calls_in(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.root = function

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is self.root:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is self.root:
                self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Call(self, node: ast.Call) -> None:
            calls.append(node)
            self.generic_visit(node)

    Visitor().visit(function)
    return calls


def _module_level_calls(tree: ast.Module) -> list[ast.Call]:
    calls: list[ast.Call] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Call(self, node: ast.Call) -> None:
            calls.append(node)
            self.generic_visit(node)

    visitor = Visitor()
    for item in tree.body:
        visitor.visit(item)
    return calls


def _instance_bindings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module: str,
    local_classes: set[str],
    imported_classes: dict[str, tuple[str, str]],
) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for node in ast.walk(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        class_ref: tuple[str, str] | None = None
        if value.func.id in local_classes:
            class_ref = (module, value.func.id)
        elif value.func.id in imported_classes:
            class_ref = imported_classes[value.func.id]
        if class_ref is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                result[target.id] = class_ref
    return result


def _resolve_callable_reference(
    node: ast.AST,
    *,
    symbol: CallableDef | None,
    module: str,
    definitions: dict[tuple[str, str], CallableDef],
    top_level: dict[tuple[str, str], tuple[str, str]],
    class_methods: dict[tuple[str, str, str], tuple[str, str]],
    nested: dict[tuple[str, str, str], tuple[str, str]],
    imported_names: dict[tuple[str, str], tuple[str, str]],
    imported_modules: dict[tuple[str, str], str],
    imported_classes: dict[tuple[str, str], tuple[str, str]],
    local_classes: set[str],
    instances: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    if isinstance(node, ast.Name):
        if symbol is not None:
            direct_nested = nested.get((module, symbol.qualified_name, node.id))
            if direct_nested:
                return direct_nested
            if symbol.enclosing_function:
                sibling = nested.get((module, symbol.enclosing_function, node.id))
                if sibling:
                    return sibling
        local = top_level.get((module, node.id))
        if local:
            return local
        imported = imported_names.get((module, node.id))
        if imported and imported in definitions:
            return imported
        return None

    if not isinstance(node, ast.Attribute):
        return None

    if isinstance(node.value, ast.Name):
        base = node.value.id
        if base in {"self", "cls"} and symbol and symbol.owner_class:
            return class_methods.get((module, symbol.owner_class, node.attr))
        if base in local_classes:
            return class_methods.get((module, base, node.attr))
        imported_class = imported_classes.get((module, base))
        if imported_class:
            return class_methods.get((*imported_class, node.attr))
        instance_class = instances.get(base)
        if instance_class:
            return class_methods.get((*instance_class, node.attr))
        imported_module = imported_modules.get((module, base))
        if imported_module:
            candidate = (imported_module, node.attr)
            if candidate in definitions:
                return candidate

    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
        class_name = node.value.func.id
        class_ref: tuple[str, str] | None = None
        if class_name in local_classes:
            class_ref = (module, class_name)
        else:
            class_ref = imported_classes.get((module, class_name))
        if class_ref:
            return class_methods.get((*class_ref, node.attr))

    return None


def _binding_from_call(
    call: ast.Call,
    *,
    owner: CallableDef | None,
    module: str,
    source: str,
    resolver: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, str], tuple[str, str] | None] | None:
    handler_keyword = next((kw for kw in call.keywords if kw.arg in _BINDING_HANDLER_KEYWORDS), None)
    if handler_keyword is None:
        return None
    identity_keyword = next((kw for kw in call.keywords if kw.arg in _BINDING_IDENTITY_KEYWORDS), None)
    identity = _literal_string(identity_keyword.value) if identity_keyword else None
    if not identity:
        return None
    target_key = resolver(handler_keyword.value)
    if target_key is None:
        return None
    constructor = _call_name(call.func) or "call"
    binding_id = f"binding:{source}:{call.lineno}:{call.col_offset}:{identity}"
    declared_fields: dict[str, Any] = {}
    for keyword in call.keywords:
        if not keyword.arg or keyword is handler_keyword or keyword is identity_keyword:
            continue
        value = _declared_value(keyword.value)
        if value is not None:
            declared_fields[keyword.arg] = value

    node = {
        "id": binding_id,
        "type": "callable_binding",
        "source": source,
        "layer": "generated",
        "name": identity,
        "constructor": constructor,
        "handler_keyword": handler_keyword.arg,
        "identity_keyword": identity_keyword.arg,
        "declared_fields": declared_fields,
        "start_line": call.lineno,
        "end_line": getattr(call, "end_lineno", call.lineno),
        "detector": "python_ast",
    }
    owner_id = owner.id if owner is not None else f"py:{module}"
    edges = [
        {
            "from": owner_id,
            "to": binding_id,
            "type": "declares_binding",
            "evidence": source,
            "start_line": call.lineno,
            "end_line": getattr(call, "end_lineno", call.lineno),
            "symbol": constructor,
            "detector": "python_ast",
            "layer": "generated",
        },
        {
            "from": binding_id,
            "to": f"fn:{target_key[0]}:{target_key[1]}",
            "type": "binds_callable",
            "evidence": source,
            "start_line": call.lineno,
            "end_line": getattr(call, "end_lineno", call.lineno),
            "symbol": identity,
            "detector": "python_ast",
            "layer": "generated",
        },
    ]
    return node, edges, target_key, owner.key if owner is not None else None


def collect_function_graph(
    subject: Path,
    overlay: dict[str, Any],
    python_by_source: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Emit only callables participating in statically proven topology."""
    roots = _root_values(overlay)
    definitions: dict[tuple[str, str], CallableDef] = {}
    trees: dict[Path, ast.Module] = {}
    symbols_by_path: dict[Path, list[CallableDef]] = {}
    imported_names: dict[tuple[str, str], tuple[str, str]] = {}
    imported_modules: dict[tuple[str, str], str] = {}
    imported_classes: dict[tuple[str, str], tuple[str, str]] = {}
    local_classes_by_module: dict[str, set[str]] = {}

    for path in _production_sources(subject, set(python_by_source)):
        source = rel(subject, path)
        module = _module_for(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        trees[path] = tree
        local_classes = {item.name for item in tree.body if isinstance(item, ast.ClassDef)}
        local_classes_by_module[module] = local_classes
        symbols = _callable_definitions(tree, module=module, source=source)
        symbols_by_path[path] = symbols
        for symbol in symbols:
            definitions[symbol.key] = symbol
        for item in tree.body:
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imported_modules[(module, alias.asname or alias.name.split(".", 1)[0])] = alias.name
            elif isinstance(item, ast.ImportFrom):
                imported_module = _from_module(module, path, item)
                if not imported_module:
                    continue
                for alias in item.names:
                    imported_names[(module, alias.asname or alias.name)] = (imported_module, alias.name)
                    imported_modules[(module, alias.asname or alias.name)] = f"{imported_module}.{alias.name}"

    top_level = {
        (module, qualified): (module, qualified)
        for (module, qualified), _symbol in definitions.items()
        if "." not in qualified
    }
    class_methods = {
        (symbol.module, symbol.owner_class, symbol.node.name): symbol.key
        for symbol in definitions.values()
        if symbol.owner_class and symbol.enclosing_function is None
    }
    nested = {
        (symbol.module, symbol.enclosing_function, symbol.node.name): symbol.key
        for symbol in definitions.values()
        if symbol.enclosing_function
    }

    for (module, alias), target in list(imported_names.items()):
        target_module, target_name = target
        if target in definitions:
            continue
        if any(
            method_module == target_module and owner == target_name
            for method_module, owner, _name in class_methods
        ):
            imported_classes[(module, alias)] = (target_module, target_name)

    call_edges: list[dict[str, Any]] = []
    binding_nodes: list[dict[str, Any]] = []
    binding_edges: list[dict[str, Any]] = []
    participants: set[tuple[str, str]] = set()

    for path, tree in trees.items():
        source = rel(subject, path)
        module = _module_for(subject, path)
        local_classes = local_classes_by_module.get(module, set())
        symbols = symbols_by_path.get(path, [])

        for symbol in symbols:
            instances = _instance_bindings(
                symbol.node,
                module=module,
                local_classes=local_classes,
                imported_classes={
                    alias: ref for (mod, alias), ref in imported_classes.items() if mod == module
                },
            )

            def resolve(node: ast.AST) -> tuple[str, str] | None:
                return _resolve_callable_reference(
                    node,
                    symbol=symbol,
                    module=module,
                    definitions=definitions,
                    top_level=top_level,
                    class_methods=class_methods,
                    nested=nested,
                    imported_names=imported_names,
                    imported_modules=imported_modules,
                    imported_classes=imported_classes,
                    local_classes=local_classes,
                    instances=instances,
                )

            for call in _calls_in(symbol.node):
                call_name = _call_name(call.func) or ""
                short_name = call_name.rsplit(".", 1)[-1]
                if short_name in {"Depends", "Inject", "Provide"}:
                    provider_node = call.args[0] if call.args else next(
                        (
                            keyword.value
                            for keyword in call.keywords
                            if keyword.arg in {"dependency", "provider", "call"}
                        ),
                        None,
                    )
                    provider_key = resolve(provider_node) if provider_node is not None else None
                    if provider_key is not None and provider_key != symbol.key:
                        participants.update((symbol.key, provider_key))
                        call_edges.append(
                            {
                                "from": symbol.id,
                                "to": f"fn:{provider_key[0]}:{provider_key[1]}",
                                "type": "injects_dependency",
                                "evidence": source,
                                "start_line": call.lineno,
                                "end_line": getattr(call, "end_lineno", call.lineno),
                                "symbol": _call_name(provider_node) if provider_node is not None else None,
                                "detector": "python_ast",
                                "layer": "generated",
                            }
                        )

                target_key = resolve(call.func)
                if target_key is not None and target_key != symbol.key:
                    participants.update((symbol.key, target_key))
                    call_edges.append(
                        {
                            "from": symbol.id,
                            "to": f"fn:{target_key[0]}:{target_key[1]}",
                            "type": "calls_function",
                            "evidence": source,
                            "start_line": call.lineno,
                            "end_line": getattr(call, "end_lineno", call.lineno),
                            "symbol": _call_name(call.func),
                            "detector": "python_ast",
                            "layer": "generated",
                        }
                    )
                binding = _binding_from_call(
                    call,
                    owner=symbol,
                    module=module,
                    source=source,
                    resolver=resolve,
                )
                if binding is not None:
                    node, edges, target_key, owner_key = binding
                    binding_nodes.append(node)
                    binding_edges.extend(edges)
                    participants.add(target_key)
                    if owner_key is not None:
                        participants.add(owner_key)

        def resolve_module(node: ast.AST) -> tuple[str, str] | None:
            return _resolve_callable_reference(
                node,
                symbol=None,
                module=module,
                definitions=definitions,
                top_level=top_level,
                class_methods=class_methods,
                nested=nested,
                imported_names=imported_names,
                imported_modules=imported_modules,
                imported_classes=imported_classes,
                local_classes=local_classes,
                instances={},
            )

        for call in _module_level_calls(tree):
            binding = _binding_from_call(
                call,
                owner=None,
                module=module,
                source=source,
                resolver=resolve_module,
            )
            if binding is not None:
                node, edges, target_key, _owner_key = binding
                binding_nodes.append(node)
                binding_edges.extend(edges)
                participants.add(target_key)

    test_edges: list[dict[str, Any]] = []
    for path in subject.rglob("*.py"):
        source = rel(subject, path)
        if skipped(subject, path) or not ({"test", "tests"} & set(Path(source).parts)):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        test_imported_functions: dict[str, tuple[str, str]] = {}
        test_imported_classes: dict[str, tuple[str, str]] = {}
        test_imported_modules: dict[str, str] = {}
        for item in tree.body:
            if isinstance(item, ast.Import):
                for alias in item.names:
                    test_imported_modules[alias.asname or alias.name.split(".", 1)[0]] = alias.name
            elif isinstance(item, ast.ImportFrom) and item.level == 0 and item.module:
                for alias in item.names:
                    key = (item.module, alias.name)
                    bound = alias.asname or alias.name
                    if key in definitions:
                        test_imported_functions[bound] = key
                        participants.add(key)
                        test_edges.append(
                            {
                                "from": f"test:{source}",
                                "to": definitions[key].id,
                                "type": "tests_function",
                                "evidence": source,
                                "start_line": item.lineno,
                                "end_line": getattr(item, "end_lineno", item.lineno),
                                "symbol": alias.name,
                                "detector": "python_ast",
                                "layer": "generated",
                            }
                        )
                    elif any(
                        mod == item.module and owner == alias.name
                        for mod, owner, _name in class_methods
                    ):
                        test_imported_classes[bound] = (item.module, alias.name)

        instances: dict[str, tuple[str, str]] = {}
        for item in ast.walk(tree):
            if not isinstance(item, (ast.Assign, ast.AnnAssign)):
                continue
            value = item.value
            if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
                continue
            class_ref = test_imported_classes.get(value.func.id)
            if class_ref is None:
                continue
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    instances[target.id] = class_ref

        seen_test_targets: set[tuple[str, str]] = set(test_imported_functions.values())
        for item in ast.walk(tree):
            if not isinstance(item, ast.Attribute):
                continue
            target_key: tuple[str, str] | None = None
            if isinstance(item.value, ast.Name):
                base = item.value.id
                class_ref = test_imported_classes.get(base) or instances.get(base)
                if class_ref:
                    target_key = class_methods.get((*class_ref, item.attr))
                elif base in test_imported_modules:
                    candidate = (test_imported_modules[base], item.attr)
                    if candidate in definitions:
                        target_key = candidate
            elif isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name):
                class_ref = test_imported_classes.get(item.value.func.id)
                if class_ref:
                    target_key = class_methods.get((*class_ref, item.attr))
            if target_key is None or target_key in seen_test_targets:
                continue
            seen_test_targets.add(target_key)
            participants.add(target_key)
            test_edges.append(
                {
                    "from": f"test:{source}",
                    "to": f"fn:{target_key[0]}:{target_key[1]}",
                    "type": "tests_function",
                    "evidence": source,
                    "start_line": item.lineno,
                    "end_line": getattr(item, "end_lineno", item.lineno),
                    "symbol": item.attr,
                    "detector": "python_ast",
                    "layer": "generated",
                }
            )

    participants.update(
        symbol.key
        for symbol in definitions.values()
        if _decorated(symbol.node)
        or symbol.node.name == "main"
        or any(symbol.source == root or symbol.source.startswith(root + "/") for root in roots)
    )

    callable_nodes: list[dict[str, Any]] = []
    for key in sorted(participants):
        symbol = definitions[key]
        node: dict[str, Any] = {
            "id": symbol.id,
            "type": "python_method" if symbol.owner_class else "python_function",
            "source": symbol.source,
            "layer": "generated",
            "name": symbol.node.name,
            "qualified_name": symbol.qualified_name,
            "module": symbol.module,
            "start_line": symbol.node.lineno,
            "end_line": getattr(symbol.node, "end_lineno", symbol.node.lineno),
            "async": isinstance(symbol.node, ast.AsyncFunctionDef),
            "detector": "python_ast",
            "route_handler": _decorated(symbol.node),
        }
        if symbol.owner_class:
            node["owner_class"] = symbol.owner_class
        if symbol.enclosing_function:
            node["enclosing_function"] = symbol.enclosing_function
        callable_nodes.append(node)

    emitted = {str(node["id"]) for node in callable_nodes}
    edges = [
        edge
        for edge in [*call_edges, *test_edges, *binding_edges]
        if edge["to"] in emitted or edge["type"] in {"declares_binding", "binds_callable"}
    ]

    emitted_bindings = {
        str(edge["to"])
        for edge in edges
        if edge["type"] == "declares_binding"
    }
    binding_nodes = [node for node in binding_nodes if str(node["id"]) in emitted_bindings]

    for key in sorted(participants):
        symbol = definitions[key]
        parent = python_by_source.get(symbol.source)
        if parent:
            edges.append(
                {
                    "from": parent,
                    "to": symbol.id,
                    "type": "defines_function",
                    "evidence": symbol.source,
                    "start_line": symbol.node.lineno,
                    "end_line": getattr(symbol.node, "end_lineno", symbol.node.lineno),
                    "symbol": symbol.qualified_name,
                    "detector": "python_ast",
                    "layer": "generated",
                }
            )

    unique_nodes = {str(node["id"]): node for node in [*callable_nodes, *binding_nodes]}
    unique_edges = {tuple(sorted(edge.items())): edge for edge in edges}
    return (
        [unique_nodes[key] for key in sorted(unique_nodes)],
        sorted(
            unique_edges.values(),
            key=lambda item: (str(item["from"]), str(item["to"]), str(item["type"])),
        ),
    )
