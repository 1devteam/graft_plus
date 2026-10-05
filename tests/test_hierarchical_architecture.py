from graft_plus.graph import build_graph


def _node(graph, node_id):
    return next(node for node in graph["nodes"] if node["id"] == node_id)


def test_repository_truth_projects_into_hierarchy_build_provenance_and_governance(tmp_path):
    engine = tmp_path / "engine"
    (engine / "native").mkdir(parents=True)
    (engine / "web").mkdir()
    (engine / "gen").mkdir()
    (tmp_path / "third_party" / "lib").mkdir(parents=True)

    (engine / "BUILD.gn").write_text(
        'sources = ["native/core.cc", "web/app.ts", "gen/generated.cc"]\n'
    )
    (engine / "web" / "BUILD.gn").write_text('sources = ["app.ts"]\n')
    (engine / "OWNERS").write_text("team@example.com\n")
    (engine / "PRESUBMIT.py").write_text("def CheckChangeOnUpload(input_api, output_api):\n    return []\n")
    (engine / "SECURITY.md").write_text("# Security\n")
    (engine / "native" / "core.cc").write_text("int core() { return 1; }\n")
    (engine / "web" / "app.ts").write_text("export const app = 1;\n")
    (engine / "gen" / "generated.cc").write_text("// GENERATED FILE - DO NOT EDIT\nint generated() { return 1; }\n")
    (tmp_path / "third_party" / "lib" / "vendor.cc").write_text("int vendor() { return 1; }\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}

    assert {"subsystem:.", "subsystem:engine", "subsystem:engine/web", "subsystem:third_party"} <= ids
    assert "build:engine/BUILD.gn" in ids
    assert "build:engine/web/BUILD.gn" in ids
    assert _node(graph, "governance:engine/OWNERS")["governance_kind"] == "ownership"
    assert _node(graph, "governance:engine/PRESUBMIT.py")["governance_kind"] == "process"
    assert _node(graph, "governance:engine/SECURITY.md")["governance_kind"] == "security"

    assert _node(graph, "native:engine/native/core.cc")["source_provenance"] == "authored"
    assert _node(graph, "native:engine/gen/generated.cc")["source_provenance"] == "generated"
    assert _node(graph, "native:third_party/lib/vendor.cc")["source_provenance"] == "vendored"
    assert _node(graph, "js:engine/web/app.ts")["subsystem"] == "engine/web"

    edge_keys = {(edge["from"], edge["to"], edge["type"]) for edge in graph["edges"]}
    assert ("subsystem:engine/web", "subsystem:engine", "member_of_subsystem") in edge_keys
    assert ("native:engine/native/core.cc", "subsystem:engine", "member_of_subsystem") in edge_keys
    assert ("js:engine/web/app.ts", "subsystem:engine/web", "member_of_subsystem") in edge_keys
    assert ("build:engine/BUILD.gn", "native:engine/native/core.cc", "declares_build_input") in edge_keys
    assert ("build:engine/BUILD.gn", "js:engine/web/app.ts", "declares_build_input") in edge_keys

    facts = graph["facts"]
    assert facts["build_definition_counts_by_system"]["gn"] == 2
    assert facts["governance_boundary_counts_by_kind"] == {"ownership": 1, "process": 1, "security": 1}
    assert facts["source_provenance_counts"]["generated"] >= 1
    assert facts["source_provenance_counts"]["vendored"] >= 1
    engine_cross = next(item for item in facts["cross_language_subsystems"] if item["subsystem"] == "engine")
    assert {"cpp", "python", "typescript"} <= set(engine_cross["languages"])

    # Cross-language relatedness is represented through shared subsystem/build truth,
    # not invented as a source-to-source dependency.
    assert not any(
        edge["from"] == "native:engine/native/core.cc"
        and edge["to"] == "js:engine/web/app.ts"
        for edge in graph["edges"]
    )
