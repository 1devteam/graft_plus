"""Tokenizer-oriented ASCII projection of canonical G.R.A.F.T. topology.

This module does not reason about the graph. It deterministically projects observed
node/edge topology into a compact ASCII representation for LLM ingestion. The
canonical JSON artifact remains available for evidence anchors and fields omitted
from the fast topology surface.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from graft_plus.residuals import canonical_json_bytes

ASCII_GRAPH_FILE = "dependency-graph.ascii.v1.txt"
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_ALPHABET_INDEX = {value: index for index, value in enumerate(_ALPHABET)}
_EDGE_CHUNK = 4096


def _width(count: int) -> int:
    if count <= 1:
        return 1
    width = 1
    capacity = len(_ALPHABET)
    while capacity < count:
        width += 1
        capacity *= len(_ALPHABET)
    return width


def _code(index: int, width: int) -> str:
    if index < 0:
        raise ValueError("index must be non-negative")
    base = len(_ALPHABET)
    chars = [_ALPHABET[0]] * width
    value = index
    for offset in range(width - 1, -1, -1):
        chars[offset] = _ALPHABET[value % base]
        value //= base
    if value:
        raise ValueError("index exceeds code width")
    return "".join(chars)


def _escape(value: object) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\p")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _unescape(value: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(value):
            raise ValueError("trailing escape in ASCII graph")
        marker = value[index + 1]
        if marker == "\\":
            out.append("\\")
        elif marker == "p":
            out.append("|")
        elif marker == "n":
            out.append("\n")
        elif marker == "r":
            out.append("\r")
        else:
            raise ValueError(f"unknown ASCII graph escape: {marker}")
        index += 2
    return "".join(out)


def _rank_types(values: list[str]) -> list[str]:
    counts = Counter(values)
    return [
        value
        for value, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def encode_graph_ascii(graph: dict[str, Any]) -> str:
    """Project graph topology into deterministic tokenizer-oriented ASCII IR."""

    nodes = sorted(
        (dict(node) for node in graph.get("nodes") or []),
        key=lambda node: str(node.get("id") or ""),
    )
    edges = sorted(
        (dict(edge) for edge in graph.get("edges") or []),
        key=lambda edge: (
            str(edge.get("from") or ""),
            str(edge.get("to") or ""),
            str(edge.get("type") or ""),
        ),
    )

    node_ids = [str(node.get("id") or "") for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("ASCII graph requires unique node ids")
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    missing = sorted(
        {
            endpoint
            for edge in edges
            for endpoint in (str(edge.get("from") or ""), str(edge.get("to") or ""))
            if endpoint not in node_index
        }
    )
    if missing:
        raise ValueError(f"ASCII graph has undefined edge endpoints: {', '.join(missing)}")

    node_types = _rank_types([str(node.get("type") or "") for node in nodes])
    edge_types = _rank_types([str(edge.get("type") or "") for edge in edges])
    type_index = {value: index for index, value in enumerate(node_types)}
    relation_index = {value: index for index, value in enumerate(edge_types)}

    node_width = _width(len(nodes))
    relation_width = _width(len(edge_types))
    type_width = _width(len(node_types))
    graph_sha = hashlib.sha256(canonical_json_bytes(graph)).hexdigest()

    lines = [
        "G1"
        f"|n={len(nodes)}"
        f"|e={len(edges)}"
        f"|nw={node_width}"
        f"|rw={relation_width}"
        f"|tw={type_width}"
        "|d=c>d"
        f"|h={graph_sha}",
    ]

    for index, value in enumerate(node_types):
        lines.append(f"T{_code(index, type_width)}={_escape(value)}")
    for index, value in enumerate(edge_types):
        lines.append(f"R{_code(index, relation_width)}={_escape(value)}")

    for index, node in enumerate(nodes):
        fields = [
            _escape(node.get("id")),
            _code(type_index[str(node.get("type") or "")], type_width),
            _escape(node.get("source")),
            _escape(node.get("subsystem")),
            _escape(node.get("layer")),
            _escape(node.get("relationship_status")),
        ]
        lines.append(f"N{_code(index, node_width)}=" + "|".join(fields))

    edge_stream = "".join(
        _code(node_index[str(edge.get("from") or "")], node_width)
        + _code(relation_index[str(edge.get("type") or "")], relation_width)
        + _code(node_index[str(edge.get("to") or "")], node_width)
        for edge in edges
    )
    if edge_stream:
        lines.append("E=" + edge_stream[:_EDGE_CHUNK])
        for offset in range(_EDGE_CHUNK, len(edge_stream), _EDGE_CHUNK):
            lines.append("E+" + edge_stream[offset : offset + _EDGE_CHUNK])
    else:
        lines.append("E=")

    return "\n".join(lines) + "\n"


def decode_graph_ascii(text: str) -> dict[str, Any]:
    """Decode the ASCII topology projection for verification and tooling."""

    lines = text.splitlines()
    if not lines or not lines[0].startswith("G1|"):
        raise ValueError("unsupported ASCII graph header")

    header: dict[str, str] = {}
    for part in lines[0].split("|")[1:]:
        key, value = part.split("=", 1)
        header[key] = value

    node_count = int(header["n"])
    edge_count = int(header["e"])
    node_width = int(header["nw"])
    relation_width = int(header["rw"])
    node_types: dict[str, str] = {}
    edge_types: dict[str, str] = {}
    nodes_by_code: dict[str, dict[str, str]] = {}
    edge_chunks: list[str] = []

    for line in lines[1:]:
        if line.startswith("T"):
            code, value = line[1:].split("=", 1)
            node_types[code] = _unescape(value)
        elif line.startswith("R"):
            code, value = line[1:].split("=", 1)
            edge_types[code] = _unescape(value)
        elif line.startswith("N"):
            code, raw = line[1:].split("=", 1)
            fields = raw.split("|")
            if len(fields) != 6:
                raise ValueError("invalid ASCII node row")
            node_id, type_code, source, subsystem, layer, relationship_status = fields
            node = {
                "id": _unescape(node_id),
                "type": node_types[type_code],
                "source": _unescape(source),
            }
            optional = {
                "subsystem": _unescape(subsystem),
                "layer": _unescape(layer),
                "relationship_status": _unescape(relationship_status),
            }
            node.update({key: value for key, value in optional.items() if value})
            nodes_by_code[code] = node
        elif line.startswith("E="):
            edge_chunks.append(line[2:])
        elif line.startswith("E+"):
            edge_chunks.append(line[2:])
        else:
            raise ValueError(f"unknown ASCII graph row: {line[:16]}")

    if len(nodes_by_code) != node_count:
        raise ValueError("ASCII graph node count mismatch")

    edge_stream = "".join(edge_chunks)
    record_width = node_width + relation_width + node_width
    if len(edge_stream) != edge_count * record_width:
        raise ValueError("ASCII graph edge stream length mismatch")

    edges: list[dict[str, str]] = []
    for offset in range(0, len(edge_stream), record_width):
        record = edge_stream[offset : offset + record_width]
        source_code = record[:node_width]
        relation_code = record[node_width : node_width + relation_width]
        target_code = record[node_width + relation_width :]
        edges.append(
            {
                "from": nodes_by_code[source_code]["id"],
                "to": nodes_by_code[target_code]["id"],
                "type": edge_types[relation_code],
            }
        )

    nodes = [
        nodes_by_code[_code(index, node_width)]
        for index in range(node_count)
    ]
    return {
        "schema_version": "ascii-topology-v1",
        "direction": header["d"],
        "source_graph_sha256": header["h"],
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "node_count": node_count,
            "edge_count": edge_count,
            "node_type_count": len(node_types),
            "edge_type_count": len(edge_types),
        },
    }
