import hashlib
import json

from graft_plus.ascii_ir import decode_graph_ascii, encode_graph_ascii
from graft_plus.cli import reconstruct
from graft_plus.graph import build_graph
from graft_plus.machine_index import build_machine_index
from graft_plus.residuals import (
    build_unresolved_ledger,
    compact_graph,
    decode_unresolved_ledger,
)


def test_unresolved_ledger_is_lossless_and_core_graph_is_compact():
    rows = [
        {"specifier": "base/memory/raw_ptr.h", "from": "a.cc"},
        {"specifier": "base/memory/raw_ptr.h", "from": "b.cc"},
        {"specifier": "./local.js", "from": "ui/a.ts"},
    ]
    ledger = build_unresolved_ledger(rows)
    assert ledger["reference_count"] == 3
    assert ledger["unique_specifier_count"] == 2
    assert decode_unresolved_ledger(ledger) == sorted(rows, key=lambda row: (row["specifier"], row["from"]))

    graph = {
        "nodes": [],
        "edges": [],
        "facts": {"unresolved_imports": rows},
        "metrics": {"node_count": 0, "edge_count": 0},
    }
    compact = compact_graph(graph, ledger)
    assert "unresolved_imports" not in compact["facts"]
    pointer = compact["facts"]["unresolved_reference_ledger"]
    assert pointer["reference_count"] == 3
    assert pointer["encoding"] == "dictionary-pairs-v1"
    assert len(pointer["sha256"]) == 64


def test_machine_index_precomputes_topology_without_recommending_changes():
    graph = {
        "nodes": [
            {"id": "a", "type": "native_module", "source": "a.cc", "subsystem": "one"},
            {"id": "b", "type": "native_module", "source": "b.cc", "subsystem": "two"},
            {"id": "c", "type": "contract", "source": "api.proto", "subsystem": "two"},
        ],
        "edges": [
            {"from": "a", "to": "b", "type": "imports"},
            {"from": "a", "to": "c", "type": "consumes_contract"},
            {"from": "b", "to": "c", "type": "consumes_contract"},
        ],
        "facts": {},
        "metrics": {},
    }
    ledger = build_unresolved_ledger([])
    index = build_machine_index(graph, ledger)
    assert index["top_dependency_fan_out"][0]["id"] == "a"
    assert index["contract_hubs"][0]["id"] == "c"
    assert index["cross_subsystem_edges"]
    assert all("recommend" not in json.dumps(row).lower() for row in index["contract_hubs"])


def test_gn_targets_and_root_native_includes_form_machine_topology(tmp_path):
    (tmp_path / "base" / "memory").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "base" / "memory" / "raw_ptr.h").write_text("struct RawPtr {};\n")
    (tmp_path / "app" / "main.cc").write_text('#include "base/memory/raw_ptr.h"\nint main() { return 0; }\n')
    (tmp_path / "app" / "util.cc").write_text("int util() { return 1; }\n")
    (tmp_path / "app" / "BUILD.gn").write_text(
        'source_set("util") {\n'
        '  sources = ["util.cc"]\n'
        '}\n'
        'executable("app") {\n'
        '  sources = ["main.cc"]\n'
        '  deps = [":util"]\n'
        '}\n'
    )

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    assert "build-target://app:util" in ids
    assert "build-target://app:app" in ids

    edge_keys = {(edge["from"], edge["to"], edge["type"]) for edge in graph["edges"]}
    assert (
        "build-target://app:app",
        "build-target://app:util",
        "depends_on_build_target",
    ) in edge_keys
    assert (
        "build-target://app:app",
        "native:app/main.cc",
        "declares_build_input",
    ) in edge_keys
    assert (
        "native:app/main.cc",
        "native:base/memory/raw_ptr.h",
        "imports",
    ) in edge_keys

    assert graph["metrics"]["build_target_count"] == 2
    assert graph["metrics"]["build_target_dependency_edge_count"] == 1
    unresolved = {
        (row["specifier"], row["from"])
        for row in graph["facts"]["unresolved_imports"]
    }
    assert ("base/memory/raw_ptr.h", "app/main.cc") not in unresolved


def test_ascii_graph_ir_round_trips_topology_and_compacts_relations():
    graph = {
        "schema_version": "1.8",
        "nodes": [
            {
                "id": "a",
                "type": "native_module",
                "source": "src/a.cc",
                "subsystem": "core",
                "evidence_anchor": {"source": "src/a.cc", "start_line": 1},
            },
            {
                "id": "b",
                "type": "native_module",
                "source": "src/b.cc",
                "subsystem": "core",
            },
            {
                "id": "c",
                "type": "contract",
                "source": "api.proto",
                "relationship_status": "parsed",
            },
        ],
        "edges": [
            {"from": "a", "to": "b", "type": "imports", "evidence": "src/a.cc"},
            {"from": "a", "to": "c", "type": "consumes_contract", "evidence": "src/a.cc"},
            {"from": "b", "to": "c", "type": "consumes_contract", "evidence": "src/b.cc"},
        ],
        "facts": {"some_large_sidecar": ["not", "duplicated", "into", "ascii"]},
        "metrics": {"node_count": 3, "edge_count": 3},
    }

    encoded = encode_graph_ascii(graph)
    decoded = decode_graph_ascii(encoded)

    assert encoded.isascii()
    assert decoded["direction"] == "c>d"
    assert decoded["metrics"]["node_count"] == 3
    assert decoded["metrics"]["edge_count"] == 3
    assert decoded["nodes"] == [
        {"id": "a", "type": "native_module", "source": "src/a.cc", "subsystem": "core"},
        {"id": "b", "type": "native_module", "source": "src/b.cc", "subsystem": "core"},
        {
            "id": "c",
            "type": "contract",
            "source": "api.proto",
            "relationship_status": "parsed",
        },
    ]
    assert decoded["edges"] == [
        {"from": "a", "to": "b", "type": "imports"},
        {"from": "a", "to": "c", "type": "consumes_contract"},
        {"from": "b", "to": "c", "type": "consumes_contract"},
    ]
    assert "evidence_anchor" not in encoded
    assert "some_large_sidecar" not in encoded


def test_cli_emits_machine_native_sidecars(tmp_path):
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "main.py").write_text("import mystery_package\n")
    out = tmp_path / "pack"
    assert reconstruct(subject, out, None, None, None) == 0

    graph = json.loads((out / "dependency-graph.v1.json").read_text())
    ascii_graph = decode_graph_ascii((out / "dependency-graph.ascii.v1.txt").read_text())
    ledger = json.loads((out / "graph-unresolved-ledger.v1.json").read_text())
    index = json.loads((out / "graph-machine-index.v1.json").read_text())
    receipt = json.loads((out / "graft-plus-receipt.json").read_text())

    assert graph["schema_version"] == "1.8"
    assert ascii_graph["metrics"]["node_count"] == graph["metrics"]["node_count"]
    assert ascii_graph["metrics"]["edge_count"] == graph["metrics"]["edge_count"]
    assert "unresolved_imports" not in graph["facts"]
    ledger_bytes = (out / "graph-unresolved-ledger.v1.json").read_bytes()
    assert graph["facts"]["unresolved_reference_ledger"]["sha256"] == hashlib.sha256(ledger_bytes).hexdigest()
    assert b"\n  " not in (out / "dependency-graph.v1.json").read_bytes()
    assert ledger["reference_count"] == 1
    assert decode_unresolved_ledger(ledger) == [
        {"specifier": "mystery_package", "from": "main.py"}
    ]
    assert index["unresolved"]["reference_count"] == 1
    assert receipt["machine_graph"] == "dependency-graph.ascii.v1.txt"
    assert receipt["machine_index"] == "graph-machine-index.v1.json"
    assert receipt["residual_ledger"] == "graph-unresolved-ledger.v1.json"
