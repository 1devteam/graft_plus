"""Source-backed runtime declaration semantics.

This collector observes literal runtime contract declarations without deciding
whether they are good, complete, relevant, safe, reachable, or merge-worthy.

It intentionally recognizes declaration *shapes* rather than repository names.
The output is a factual layer for receiving models to reason over.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

_SKIP = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
_JOB_IDENTITY_FIELDS = ("job_key", "key", "name", "id")
_JOB_COLLECTION_FIELDS = ("required_inputs", "produced_outputs", "candidate_actions")
_ACTION_CONTRACT_FIELDS = frozenset(
    {"input_model", "provider", "side_effect_class", "credential_requirement"}
)


def _rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def _skip(path: Path) -> bool:
    return any(part in _SKIP for part in path.parts)


def _production_py(subject: Path) -> list[Path]:
    result: list[Path] = []
    for path in subject.rglob("*.py"):
        if _skip(path):
            continue
        rel = _rel(subject, path)
        if {"tests", "test", "fixtures", "migrations", "alembic"} & set(Path(rel).parts):
            continue
        result.append(path)
    return sorted(result)


def _module_for(subject: Path, path: Path) -> str:
    parts = list(path.relative_to(subject).with_suffix("").parts)
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


def _constructor_name(call: ast.Call) -> str:
    return (_call_name(call.func) or "").rsplit(".", 1)[-1]


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_strings(node: ast.AST | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = tuple(_literal_string(item) for item in node.elts)
        return tuple(value for value in values if value) if all(values) else ()
    value = _literal_string(node)
    return (value,) if value else ()


def _declared_value(node: ast.AST | None) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_declared_value(item) for item in node.elts]
        if all(value is not None for value in values):
            return values
        return None
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=False):
            key = _literal_string(key_node)
            value = _declared_value(value_node)
            if key is None or value is None:
                return None
            result[key] = value
        return result
    name = _call_name(node)
    if name:
        return {"symbol": name}
    if isinstance(node, ast.Call):
        call_name = _call_name(node.func)
        if call_name:
            result: dict[str, Any] = {"call": call_name}
            keywords: dict[str, Any] = {}
            for keyword in node.keywords:
                if not keyword.arg:
                    continue
                value = _declared_value(keyword.value)
                if value is not None:
                    keywords[keyword.arg] = value
            if keywords:
                result["keywords"] = keywords
            return result
    try:
        rendered = ast.unparse(node).strip()
    except (AttributeError, ValueError):
        return None
    return {"expression": rendered[:240]} if rendered else None


def _identity(call: ast.Call) -> str | None:
    for field in _JOB_IDENTITY_FIELDS:
        value = _literal_string(_keyword(call, field))
        if value:
            return value
    return None


def _job_shape(call: ast.Call) -> bool:
    present = {keyword.arg for keyword in call.keywords if keyword.arg}
    if "candidate_actions" in present:
        return True
    return {"required_inputs", "produced_outputs"} <= present


def _dependency_rows(node: ast.AST | None) -> list[dict[str, Any]]:
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return []
    result: list[dict[str, Any]] = []
    for item in node.elts:
        if not isinstance(item, ast.Call):
            continue
        identity = _identity(item)
        if not identity:
            continue
        row: dict[str, Any] = {
            "job_key": identity,
            "constructor": _constructor_name(item),
        }
        for keyword in item.keywords:
            if not keyword.arg:
                continue
            value = _declared_value(keyword.value)
            if value is not None:
                row[keyword.arg] = value
        result.append(row)
    return result


def _job_records(subject: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _production_py(subject):
        source = _rel(subject, path)
        module = _module_for(subject, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _job_shape(node):
                continue
            identity = _identity(node)
            if not identity:
                continue
            declared_fields: dict[str, Any] = {}
            for keyword in node.keywords:
                if not keyword.arg:
                    continue
                value = _declared_value(keyword.value)
                if value is not None:
                    declared_fields[keyword.arg] = value
            records.append(
                {
                    "job_key": identity,
                    "constructor": _constructor_name(node),
                    "source": source,
                    "module": module,
                    "start_line": int(getattr(node, "lineno", 1)),
                    "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
                    "required_inputs": _literal_strings(_keyword(node, "required_inputs")),
                    "produced_outputs": _literal_strings(_keyword(node, "produced_outputs")),
                    "candidate_actions": _literal_strings(_keyword(node, "candidate_actions")),
                    "dependencies": _dependency_rows(_keyword(node, "dependencies")),
                    "declared_fields": declared_fields,
                }
            )
    return sorted(
        records,
        key=lambda row: (str(row["job_key"]), str(row["source"]), int(row["start_line"])),
    )


def _symbol_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        symbol = value.get("symbol")
        if isinstance(symbol, str):
            return symbol
    return None


def _add_or_merge_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    node_id = str(node["id"])
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = node
        return
    sources = sorted(
        {
            str(value)
            for value in (
                existing.get("source"),
                node.get("source"),
                *(existing.get("sources") or []),
                *(node.get("sources") or []),
            )
            if value
        }
    )
    if sources:
        existing["source"] = sources[0]
        if len(sources) > 1:
            existing["sources"] = sources
    for key, value in node.items():
        if key in {"id", "source", "sources"} or value in (None, "", [], {}):
            continue
        if key not in existing:
            existing[key] = value


def _runtime_action_nodes(
    function_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    actions: dict[str, dict[str, Any]] = {}

    for binding in function_nodes:
        if binding.get("type") != "callable_binding":
            continue
        declared_fields = binding.get("declared_fields")
        if not isinstance(declared_fields, dict):
            declared_fields = {}
        constructor = str(binding.get("constructor") or "")
        actionish = "action" in constructor.lower() or bool(_ACTION_CONTRACT_FIELDS & set(declared_fields))
        identity = str(binding.get("name") or "")
        if not actionish or not identity:
            continue

        source = str(binding.get("source") or "")
        action_id = f"action:{identity}"
        action_node: dict[str, Any] = {
            "id": action_id,
            "type": "runtime_action",
            "name": identity,
            "source": source,
            "layer": "generated",
            "constructor": constructor,
            "declared_fields": declared_fields,
            "detector": "python_literal_runtime_declaration",
        }
        _add_or_merge_node(nodes, action_node)
        actions[identity] = nodes[action_id]
        edges.append(
            {
                "from": action_id,
                "to": str(binding["id"]),
                "type": "declared_by",
                "evidence": source,
                "start_line": binding.get("start_line"),
                "end_line": binding.get("end_line"),
                "detector": "python_literal_runtime_declaration",
                "layer": "generated",
            }
        )

        input_model = _symbol_name(declared_fields.get("input_model"))
        if input_model:
            input_id = f"input-contract:{input_model}"
            _add_or_merge_node(
                nodes,
                {
                    "id": input_id,
                    "type": "runtime_input_contract",
                    "name": input_model,
                    "source": source,
                    "layer": "generated",
                    "detector": "python_literal_runtime_declaration",
                },
            )
            edges.append(
                {
                    "from": action_id,
                    "to": input_id,
                    "type": "declares_input_model",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        side_effect = _symbol_name(declared_fields.get("side_effect_class"))
        if side_effect:
            side_effect_id = f"side-effect-class:{side_effect}"
            _add_or_merge_node(
                nodes,
                {
                    "id": side_effect_id,
                    "type": "side_effect_class",
                    "name": side_effect,
                    "source": source,
                    "layer": "generated",
                    "detector": "python_literal_runtime_declaration",
                },
            )
            edges.append(
                {
                    "from": action_id,
                    "to": side_effect_id,
                    "type": "declares_side_effect_class",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        provider = declared_fields.get("provider")
        if isinstance(provider, str) and provider:
            provider_id = f"provider:{provider}"
            _add_or_merge_node(
                nodes,
                {
                    "id": provider_id,
                    "type": "runtime_provider",
                    "name": provider,
                    "source": source,
                    "layer": "generated",
                    "detector": "python_literal_runtime_declaration",
                },
            )
            edges.append(
                {
                    "from": action_id,
                    "to": provider_id,
                    "type": "uses_provider",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        credential = declared_fields.get("credential_requirement")
        if isinstance(credential, dict):
            credential_id = f"credential-requirement:{identity}"
            credential_node = {
                "id": credential_id,
                "type": "credential_requirement",
                "name": identity,
                "source": source,
                "layer": "generated",
                "declaration": credential,
                "detector": "python_literal_runtime_declaration",
            }
            _add_or_merge_node(nodes, credential_node)
            edges.append(
                {
                    "from": action_id,
                    "to": credential_id,
                    "type": "requires_credential",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )
            keywords = credential.get("keywords")
            credential_provider = keywords.get("provider") if isinstance(keywords, dict) else None
            if isinstance(credential_provider, str) and credential_provider:
                provider_id = f"provider:{credential_provider}"
                _add_or_merge_node(
                    nodes,
                    {
                        "id": provider_id,
                        "type": "runtime_provider",
                        "name": credential_provider,
                        "source": source,
                        "layer": "generated",
                        "detector": "python_literal_runtime_declaration",
                    },
                )
                edges.append(
                    {
                        "from": credential_id,
                        "to": provider_id,
                        "type": "credential_for_provider",
                        "evidence": source,
                        "detector": "python_literal_runtime_declaration",
                        "layer": "generated",
                    }
                )

    return list(nodes.values()), edges, actions


def collect_runtime_declarations(
    subject: Path,
    function_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return literal runtime declaration facts and topology."""

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    action_nodes, action_edges, actions = _runtime_action_nodes(function_nodes)
    for node in action_nodes:
        _add_or_merge_node(nodes, node)
    edges.extend(action_edges)

    jobs = _job_records(subject)
    produced_outputs = {
        output
        for job in jobs
        for output in job["produced_outputs"]
        if isinstance(output, str) and output
    }
    declared_jobs = {str(job["job_key"]) for job in jobs}

    for job in jobs:
        key = str(job["job_key"])
        source = str(job["source"])
        job_id = f"job:{key}"
        _add_or_merge_node(
            nodes,
            {
                "id": job_id,
                "type": "business_job",
                "name": key,
                "source": source,
                "layer": "generated",
                "constructor": job["constructor"],
                "declared_fields": job["declared_fields"],
                "start_line": job["start_line"],
                "end_line": job["end_line"],
                "detector": "python_literal_runtime_declaration",
            },
        )
        module = str(job["module"])
        if module:
            edges.append(
                {
                    "from": job_id,
                    "to": f"py:{module}",
                    "type": "declared_in",
                    "evidence": source,
                    "start_line": job["start_line"],
                    "end_line": job["end_line"],
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        for output in job["produced_outputs"]:
            artifact_id = f"artifact:{output}"
            _add_or_merge_node(
                nodes,
                {
                    "id": artifact_id,
                    "type": "runtime_artifact",
                    "name": output,
                    "source": source,
                    "layer": "generated",
                    "detector": "python_literal_runtime_declaration",
                },
            )
            edges.append(
                {
                    "from": artifact_id,
                    "to": job_id,
                    "type": "produced_by",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        for input_name in job["required_inputs"]:
            if input_name in produced_outputs:
                target = f"artifact:{input_name}"
                edge_type = "requires_artifact"
                _add_or_merge_node(
                    nodes,
                    {
                        "id": target,
                        "type": "runtime_artifact",
                        "name": input_name,
                        "source": source,
                        "layer": "generated",
                        "detector": "python_literal_runtime_declaration",
                    },
                )
            else:
                target = f"input:{input_name}"
                edge_type = "requires_input"
                _add_or_merge_node(
                    nodes,
                    {
                        "id": target,
                        "type": "runtime_input",
                        "name": input_name,
                        "source": source,
                        "layer": "generated",
                        "detector": "python_literal_runtime_declaration",
                    },
                )
            edges.append(
                {
                    "from": job_id,
                    "to": target,
                    "type": edge_type,
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        for action_name in job["candidate_actions"]:
            action_id = f"action:{action_name}"
            _add_or_merge_node(
                nodes,
                actions.get(action_name)
                or {
                    "id": action_id,
                    "type": "runtime_action",
                    "name": action_name,
                    "source": source,
                    "layer": "generated",
                    "observation": "candidate_action",
                    "detector": "python_literal_runtime_declaration",
                },
            )
            edges.append(
                {
                    "from": job_id,
                    "to": action_id,
                    "type": "candidate_action",
                    "evidence": source,
                    "detector": "python_literal_runtime_declaration",
                    "layer": "generated",
                }
            )

        for dependency in job["dependencies"]:
            dependency_key = str(dependency["job_key"])
            dependency_id = f"job:{dependency_key}"
            if dependency_key not in declared_jobs:
                _add_or_merge_node(
                    nodes,
                    {
                        "id": dependency_id,
                        "type": "business_job_reference",
                        "name": dependency_key,
                        "source": source,
                        "layer": "generated",
                        "detector": "python_literal_runtime_declaration",
                    },
                )
            edge: dict[str, Any] = {
                "from": job_id,
                "to": dependency_id,
                "type": "depends_on_job",
                "evidence": source,
                "detector": "python_literal_runtime_declaration",
                "layer": "generated",
            }
            kind = dependency.get("kind")
            if isinstance(kind, str) and kind:
                edge["dependency_kind"] = kind
            edges.append(edge)

    ordered_nodes = sorted(nodes.values(), key=lambda node: str(node["id"]))
    ordered_edges = sorted(
        edges,
        key=lambda edge: (
            str(edge.get("from") or ""),
            str(edge.get("to") or ""),
            str(edge.get("type") or ""),
        ),
    )
    counts = defaultdict(int)
    for node in ordered_nodes:
        counts[str(node.get("type") or "unknown")] += 1
    return {
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "facts": {
            "runtime_declaration_node_counts": dict(sorted(counts.items())),
            "runtime_declaration_edge_count": len(ordered_edges),
        },
    }
