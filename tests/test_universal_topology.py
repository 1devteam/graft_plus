import json

from graft_plus.completeness import audit
from graft_plus.graph import build_graph


def _edge(graph, source, target, kind):
    return any(
        edge["from"] == source and edge["to"] == target and edge["type"] == kind
        for edge in graph["edges"]
    )


def test_commonjs_package_and_test_topology(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-cli",
                "description": "A declared command-line tool",
                "main": "index.js",
                "bin": {"sample": "lib/cli.js"},
                "dependencies": {"commander": "^12.0.0"},
            }
        )
    )
    (tmp_path / "index.js").write_text("module.exports = require('./lib/cli')\n")
    (tmp_path / "lib" / "cli.js").write_text("const command = require('./command')\n")
    (tmp_path / "lib" / "command.js").write_text("module.exports = () => 1\n")
    (tmp_path / "test" / "cli.test.js").write_text("const cli = require('../lib/cli')\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}

    assert {"js:index.js", "js:lib/cli.js", "js:lib/command.js", "test:test/cli.test.js"} <= ids
    assert {"package:sample-cli", "dependency:commander"} <= ids
    assert _edge(graph, "js:index.js", "js:lib/cli.js", "imports")
    assert _edge(graph, "js:lib/cli.js", "js:lib/command.js", "imports")
    assert _edge(graph, "test:test/cli.test.js", "js:lib/cli.js", "tests")
    assert _edge(graph, "package:sample-cli", "js:index.js", "declares_entrypoint")
    assert _edge(graph, "package:sample-cli", "dependency:commander", "depends_on_package")


def test_shell_bats_python_and_intent_topology(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "ralph_loop.sh").write_text(
        "#!/usr/bin/env bash\n"
        "SCRIPT_DIR=$(cd -- \"$(dirname -- \"$0\")\" && pwd)\n"
        "source \"$SCRIPT_DIR/lib/queue.sh\"\n"
        "python3 \"$SCRIPT_DIR/lib/e2b_helper.py\"\n"
    )
    (tmp_path / "lib" / "queue.sh").write_text("#!/usr/bin/env bash\nnext_item() { :; }\n")
    (tmp_path / "lib" / "e2b_helper.py").write_text("def run():\n    return 1\n")
    (tmp_path / "tests" / "loop.bats").write_text("load '../lib/queue.sh'\n@test \"loop\" { true; }\n")
    (tmp_path / "README.md").write_text("# Ralph\n")
    (tmp_path / "docs" / "architecture" / "design.md").write_text("# Design\n")

    graph = build_graph(subject=tmp_path)

    assert _edge(graph, "sh:ralph_loop.sh", "sh:lib/queue.sh", "sources")
    assert _edge(graph, "sh:ralph_loop.sh", "py:lib.e2b_helper", "invokes")
    assert _edge(graph, "test:tests/loop.bats", "sh:lib/queue.sh", "tests")
    intent = {(item["path"], item["kind"]) for item in graph["facts"]["intent_sources"]}
    assert ("README.md", "readme") in intent
    assert ("docs/architecture/design.md", "declared-intent") in intent
    assert graph["facts"]["file_count"] >= 6


def test_function_topology_is_overlay_selected(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "flow.py").write_text(
        "def load():\n    return 1\n\n"
        "def run():\n    return load()\n"
    )
    (tmp_path / "tests" / "test_flow.py").write_text("from app.flow import run\n\ndef test_run():\n    assert run()\n")
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"function_roots": ["app"]}))

    graph = build_graph(subject=tmp_path, overlay_path=overlay)

    assert _edge(graph, "py:app.flow", "fn:app.flow:run", "defines_function")
    assert _edge(graph, "fn:app.flow:run", "fn:app.flow:load", "calls_function")
    assert _edge(graph, "test:tests/test_flow.py", "fn:app.flow:run", "tests_function")


def test_unknown_language_is_inventoried_without_inventing_relationships(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")

    graph = build_graph(subject=tmp_path)
    completeness = audit(graph, subject=tmp_path)

    node = next(node for node in graph["nodes"] if node["id"] == "file:main.go")
    assert node["relationship_status"] == "inventory_only"
    assert graph["facts"]["relationship_unparsed_files"] == ["main.go"]
    assert completeness["residuals"]["relationship_unparsed_files"] == ["main.go"]
    assert completeness["integrity_pass"] is True


def test_every_edge_endpoint_is_defined(tmp_path):
    (tmp_path / "index.js").write_text("module.exports = 1\n")
    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    assert all(edge["from"] in ids and edge["to"] in ids for edge in graph["edges"])
    assert len(ids) == len(graph["nodes"])
