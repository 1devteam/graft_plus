"""Configuration and deployment facts with names only, never secret values."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from graft_plus.boundaries import mask_noncode
from graft_plus.inventory import rel, relevant_files

_ENV_NAME = r"[A-Z][A-Z0-9_]{1,127}"
_JS_ENV_RE = re.compile(rf"\b(?:process\.env\.({_ENV_NAME})|process\.env\[['\"]({_ENV_NAME})['\"]\])")
_SHELL_ENV_RE = re.compile(rf"\$(?:\{{({_ENV_NAME})(?::-[^}}]*)?\}}|({_ENV_NAME})\b)")
_ENV_DECL_RE = re.compile(rf"^\s*(?:export\s+)?({_ENV_NAME})\s*=", re.M)
_YAML_KEY_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$")
_DOCKER_INSTRUCTION_RE = re.compile(r"^\s*(ENV|EXPOSE|CMD|ENTRYPOINT|VOLUME|HEALTHCHECK)\b\s*(.*)$", re.I)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _literal(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _python_reads(text: str, source: str) -> list[tuple[str, int, str]]:
    try:
        tree = ast.parse(text, filename=source)
    except SyntaxError:
        return []
    rows: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in {"os.getenv", "os.environ.get", "environ.get"}:
            name = _literal(node.args[0] if node.args else None)
            if name and re.fullmatch(_ENV_NAME, name):
                rows.append((name, node.lineno, "python_ast"))
        elif isinstance(node, ast.Subscript) and _call_name(node.value) in {"os.environ", "environ"}:
            name = _literal(node.slice)
            if name and re.fullmatch(_ENV_NAME, name):
                rows.append((name, node.lineno, "python_ast"))
    return rows


def _line_reads(text: str, suffix: str) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    if suffix in {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}:
        code = mask_noncode(text, "javascript")
        for match in _JS_ENV_RE.finditer(text):
            if not code[match.start() :].startswith("process.env"):
                continue
            name = next((value for value in match.groups() if value), None)
            if name:
                rows.append((name, text.count("\n", 0, match.start()) + 1, "javascript_env_reference"))
        return rows
    lines = text.splitlines()
    local_assignments: set[str] = set()
    for line in lines:
        assignment = re.match(rf"^\s*(?:(?:local|declare|readonly|export)\s+)?({_ENV_NAME})\s*=", line)
        if assignment:
            name = assignment.group(1)
            if not re.search(rf"\$(?:\{{{re.escape(name)}(?:[:}}])|{re.escape(name)}\b)", line):
                local_assignments.add(name)
        loop = re.match(rf"^\s*for\s+({_ENV_NAME})\s+in\b", line)
        if loop:
            local_assignments.add(loop.group(1))
    for number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "#")):
            continue
        for match in _SHELL_ENV_RE.finditer(line):
            name = next((value for value in match.groups() if value), None)
            if name and name not in local_assignments:
                rows.append((name, number, "shell_env_reference"))
    return rows


def _owner_node(
    source: str,
    source_node_ids: dict[str, str],
    nodes: dict[str, dict[str, Any]],
) -> str:
    existing = source_node_ids.get(source)
    if existing:
        return existing
    node_id = f"file:{source}"
    nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "type": "configuration",
            "source": source,
            "layer": "generated",
            "relationship_status": "parsed",
            "detector": "configuration_parser",
        },
    )
    return node_id


def _yaml_deployment(text: str, source: str) -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    facts: list[dict[str, Any]] = []
    environment: list[tuple[str, int]] = []
    stack: list[tuple[int, str]] = []
    structural = {"command", "entrypoint", "healthcheck", "inputs", "outputs", "ports", "services", "volumes"}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _YAML_KEY_RE.match(line)
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parents = [name for _, name in stack]
        if match:
            key, remainder = match.group(2), match.group(3).strip()
            lower = key.lower()
            if lower in structural:
                facts.append(
                    {"kind": lower, "source": source, "line": number, "detector": "yaml_structure_lexer"}
                )
            if "services" in parents and parents[-1] == "services":
                facts.append(
                    {
                        "kind": "service",
                        "name": key,
                        "source": source,
                        "line": number,
                        "detector": "yaml_structure_lexer",
                    }
                )
            if parents and parents[-1] in {"inputs", "outputs"}:
                facts.append(
                    {
                        "kind": parents[-1][:-1],
                        "name": key,
                        "source": source,
                        "line": number,
                        "detector": "yaml_structure_lexer",
                    }
                )
            if parents and parents[-1] in {"env", "environment"} and re.fullmatch(_ENV_NAME, key):
                environment.append((key, number))
            if not remainder:
                stack.append((indent, lower))
            continue
        if stack and stack[-1][1] == "ports":
            value = line.strip().removeprefix("-").strip().strip("'\"")
            if re.fullmatch(r"[0-9.:/-]+", value):
                facts.append(
                    {
                        "kind": "port",
                        "name": value,
                        "source": source,
                        "line": number,
                        "detector": "yaml_structure_lexer",
                    }
                )
    return facts, environment


def _docker_deployment(text: str, source: str) -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    facts: list[dict[str, Any]] = []
    environment: list[tuple[str, int]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _DOCKER_INSTRUCTION_RE.match(line)
        if not match or line.lstrip().startswith("#"):
            continue
        instruction, value = match.group(1).lower(), match.group(2).strip()
        row: dict[str, Any] = {
            "kind": instruction,
            "source": source,
            "line": number,
            "detector": "dockerfile_instruction_parser",
        }
        if instruction == "expose":
            ports = " ".join(part for part in value.split() if re.fullmatch(r"\d+(?:/(?:tcp|udp))?", part))
            if ports:
                row["name"] = ports
        facts.append(row)
        if instruction == "env":
            env_match = re.match(rf"({_ENV_NAME})(?:\s*=|\s+)", value)
            if env_match:
                environment.append((env_match.group(1), number))
    return facts, environment


def collect_configuration_graph(
    subject: Path,
    source_node_ids: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Collect environment names and deployment structure without values."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    deployment: list[dict[str, Any]] = []

    def config_node(name: str, source: str) -> str:
        node_id = f"config:key:{name}"
        nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "type": "configuration_key",
                "source": source,
                "layer": "generated",
                "name": name,
                "feature_flag": name.startswith(("FEATURE_", "ENABLE_", "DISABLE_")),
                "detector": "configuration_parser",
            },
        )
        return node_id

    for path in relevant_files(subject):
        source = rel(subject, path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        suffix = path.suffix.lower()
        reads: list[tuple[str, int, str]] = []
        if suffix == ".py":
            reads = _python_reads(text, source)
        elif suffix in {".bash", ".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".sh", ".ts", ".tsx", ".zsh"}:
            reads = _line_reads(text, suffix)
        owner = source_node_ids.get(source)
        if owner:
            for name, line, detector in reads:
                edges.append(
                    {
                        "from": owner,
                        "to": config_node(name, source),
                        "type": "reads_config",
                        "evidence": source,
                        "start_line": line,
                        "end_line": line,
                        "symbol": name,
                        "detector": detector,
                        "layer": "generated",
                    }
                )

        declaration_file = path.name == ".env.example"
        deployment_file = path.name.startswith("Dockerfile") or path.name in {"docker-compose.yml", "docker-compose.yaml"} or source.startswith(".github/workflows/")
        if declaration_file:
            file_owner = _owner_node(source, source_node_ids, nodes)
            for match in _ENV_DECL_RE.finditer(text):
                name = match.group(1)
                line = text.count("\n", 0, match.start()) + 1
                edges.append(
                    {
                        "from": file_owner,
                        "to": config_node(name, source),
                        "type": "declares_config",
                        "evidence": source,
                        "start_line": line,
                        "end_line": line,
                        "symbol": name,
                        "detector": "env_example_parser",
                        "layer": "generated",
                    }
                )
        if deployment_file:
            file_owner = _owner_node(source, source_node_ids, nodes)
            rows, environment = (
                _docker_deployment(text, source)
                if path.name.startswith("Dockerfile")
                else _yaml_deployment(text, source)
            )
            deployment.extend(rows)
            for name, number in environment:
                edges.append(
                    {
                        "from": file_owner,
                        "to": config_node(name, source),
                        "type": "declares_config",
                        "evidence": source,
                        "start_line": number,
                        "end_line": number,
                        "symbol": name,
                        "detector": "deployment_env_parser",
                        "layer": "generated",
                    }
                )

    unique_edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (str(edge["from"]), str(edge["to"]), str(edge["type"]), str(edge["evidence"]))
        unique_edges.setdefault(key, edge)
    counts = Counter(str(row["kind"]) for row in deployment)
    return sorted(nodes.values(), key=lambda row: str(row["id"])), sorted(
        unique_edges.values(),
        key=lambda row: (str(row["from"]), str(row["to"]), str(row["type"]), int(row["start_line"])),
    ), {
        "deployment_facts": sorted(deployment, key=lambda row: (row["source"], row["line"], row["kind"])),
        "deployment_fact_count": len(deployment),
        "deployment_fact_counts_by_kind": dict(sorted(counts.items())),
        "configuration_key_count": sum(1 for node in nodes.values() if node["type"] == "configuration_key"),
    }
