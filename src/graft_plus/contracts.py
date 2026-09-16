"""Source-backed declaration topology for portable contract files."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from graft_plus.inventory import CONTRACT_SUFFIXES, language, rel, relevant_files

_PROTO_DECL_RE = re.compile(r"^\s*(message|enum|service)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_PROTO_RPC_RE = re.compile(r"\brpc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PROTO_IMPORT_RE = re.compile(r'^\s*import\s+(?:public\s+|weak\s+)?["\']([^"\']+)["\']\s*;', re.M)
_GRAPHQL_DECL_RE = re.compile(
    r"^\s*(type|input|interface|enum|scalar|union|schema)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
_GRAPHQL_ROOT_RE = re.compile(r"\btype\s+(Query|Mutation|Subscription)\b[^\{]*\{(.*?)\}", re.S)
_GRAPHQL_FIELD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:", re.M)
_SQL_DECL_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[\"`]?([A-Za-z_][A-Za-z0-9_]*)[\"`]?\.)?[\"`]?([A-Za-z_][A-Za-z0-9_]*)[\"`]?",
    re.I,
)
_QUOTED_CONTRACT_RE = re.compile(r"[\"']([^\"']+\.(?:avsc|gql|graphql|proto|sql))[\"']", re.I)


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blank_match(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _declaration(source: str, kind: str, name: str, line: int, *, parent: str | None = None) -> dict[str, Any]:
    identity = f"{parent}.{name}" if parent else name
    return {
        "id": f"contract:{kind}:{source}:{identity}",
        "type": "contract",
        "source": source,
        "layer": "generated",
        "name": name,
        "kind": kind,
        "parent": parent,
        "start_line": line,
        "end_line": line,
        "detector": "contract_parser",
    }


def _avro_records(value: Any, source: str, rows: list[dict[str, Any]], line_by_name: dict[str, int]) -> None:
    if isinstance(value, dict):
        if value.get("type") in {"record", "enum", "fixed"} and isinstance(value.get("name"), str):
            name = str(value["name"])
            rows.append(_declaration(source, f"avro_{value['type']}", name, line_by_name.get(name, 1)))
        for child in value.values():
            _avro_records(child, source, rows, line_by_name)
    elif isinstance(value, list):
        for child in value:
            _avro_records(child, source, rows, line_by_name)


def _parse(path: Path, source: str, text: str) -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    rows: list[dict[str, Any]] = []
    imports: list[tuple[str, int]] = []
    suffix = path.suffix.lower()
    if suffix == ".proto":
        for match in _PROTO_DECL_RE.finditer(text):
            rows.append(_declaration(source, f"protobuf_{match.group(1)}", match.group(2), _line(text, match.start())))
        for match in _PROTO_RPC_RE.finditer(text):
            rows.append(_declaration(source, "protobuf_rpc", match.group(1), _line(text, match.start())))
        imports.extend((match.group(1), _line(text, match.start())) for match in _PROTO_IMPORT_RE.finditer(text))
    elif suffix in {".gql", ".graphql"}:
        clean = re.sub(r'""".*?"""', _blank_match, text, flags=re.S)
        clean = re.sub(r"#.*$", _blank_match, clean, flags=re.M)
        for match in _GRAPHQL_DECL_RE.finditer(clean):
            rows.append(_declaration(source, f"graphql_{match.group(1)}", match.group(2), _line(clean, match.start())))
        for root in _GRAPHQL_ROOT_RE.finditer(clean):
            body_offset = root.start(2)
            for field in _GRAPHQL_FIELD_RE.finditer(root.group(2)):
                rows.append(
                    _declaration(
                        source,
                        "graphql_operation",
                        field.group(1),
                        _line(clean, body_offset + field.start()),
                        parent=root.group(1),
                    )
                )
    elif suffix == ".sql":
        clean = re.sub(r"/\*.*?\*/", _blank_match, text, flags=re.S)
        clean = re.sub(r"--.*$", _blank_match, clean, flags=re.M)
        for match in _SQL_DECL_RE.finditer(clean):
            qualified = f"{match.group(2)}.{match.group(3)}" if match.group(2) else match.group(3)
            rows.append(_declaration(source, f"sql_{match.group(1).lower()}", qualified, _line(clean, match.start())))
    elif suffix == ".avsc":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return [], []
        line_by_name = {
            match.group(1): _line(text, match.start())
            for match in re.finditer(r'"name"\s*:\s*"([^"]+)"', text)
        }
        _avro_records(payload, source, rows, line_by_name)
    return rows, imports


def _resolve_contract(source_path: Path, value: str, known: set[Path], subject: Path) -> Path | None:
    candidates = {(source_path.parent / value).resolve(), (subject / value).resolve()}
    hits = sorted(candidate for candidate in candidates if candidate in known)
    return hits[0] if len(hits) == 1 else None


def _mask_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", _blank_match, text, flags=re.S)
    return re.sub(r"//.*$", _blank_match, text, flags=re.M)


def _source_references(path: Path, source: str, text: str) -> list[tuple[str, int]]:
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(text, filename=source)
        except SyntaxError:
            return []
        return [
            (node.value, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(r"\.(?:avsc|gql|graphql|proto|sql)$", node.value, re.I)
        ]
    code = _mask_comments(text)
    return [(match.group(1), _line(code, match.start())) for match in _QUOTED_CONTRACT_RE.finditer(code)]


def collect_contract_file_graph(
    subject: Path,
    source_node_ids: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Parse contract declarations, imports, and literal source consumers."""
    files = {path.resolve() for path in relevant_files(subject) if path.suffix.lower() in CONTRACT_SUFFIXES}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    declarations: list[dict[str, Any]] = []
    for path in sorted(files):
        source = rel(subject, path)
        file_id = f"file:{source}"
        nodes.append(
            {
                "id": file_id,
                "type": "contract_source",
                "source": source,
                "layer": "generated",
                "language": language(path),
                "relationship_status": "parsed",
                "detector": "contract_parser",
            }
        )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parsed, imports = _parse(path, source, text)
        declarations.extend(parsed)
        for node in parsed:
            edges.append(
                {
                    "from": file_id,
                    "to": node["id"],
                    "type": "defines_contract",
                    "evidence": source,
                    "start_line": node["start_line"],
                    "end_line": node["end_line"],
                    "symbol": node["name"],
                    "detector": "contract_parser",
                    "layer": "generated",
                }
            )
        for value, line in imports:
            target = _resolve_contract(path, value, files, subject)
            if target is not None:
                edges.append(
                    {
                        "from": file_id,
                        "to": f"file:{rel(subject, target)}",
                        "type": "imports_contract",
                        "evidence": source,
                        "start_line": line,
                        "end_line": line,
                        "symbol": value,
                        "detector": "contract_parser",
                        "layer": "generated",
                    }
                )
    nodes.extend(declarations)

    for source, source_id in sorted(source_node_ids.items()):
        path = (subject / source).resolve()
        if path in files or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for value, line in _source_references(path, source, text):
            target = _resolve_contract(path, value, files, subject)
            if target is None:
                continue
            edges.append(
                {
                    "from": source_id,
                    "to": f"file:{rel(subject, target)}",
                    "type": "consumes_contract",
                    "evidence": source,
                    "start_line": line,
                    "end_line": line,
                    "symbol": value,
                    "detector": "literal_contract_reference",
                    "layer": "generated",
                }
            )
    node_by_id = {str(node["id"]): node for node in nodes}
    nodes = [node_by_id[node_id] for node_id in sorted(node_by_id)]
    return nodes, edges, {
        "contract_source_count": len(files),
        "contract_declaration_count": sum(1 for node in nodes if node["type"] == "contract"),
        "contract_declaration_counts_by_kind": dict(
            sorted(
                (kind, sum(1 for row in nodes if row.get("kind") == kind))
                for kind in {str(row["kind"]) for row in nodes if row.get("kind")}
            )
        ),
    }
