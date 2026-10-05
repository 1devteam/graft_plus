from graft_plus.completeness import audit
from graft_plus.decision import decide
from graft_plus.graph import build_graph


def test_mock_patch_is_not_http_patch_route(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "worker.py").write_text("from unittest import mock\n@mock.patch('subprocess.run')\ndef execute(fake_run):\n    return fake_run\n")
    graph = build_graph(subject=tmp_path)
    assert not any(node["type"] == "http_route" and node.get("method") == "PATCH" for node in graph["nodes"])


def test_duplicate_canonical_identity_blocks_assurance():
    graph = {"nodes": [{"id": "py:dup", "type": "python_module", "source": "a.py", "layer": "generated"}, {"id": "py:dup", "type": "python_module", "source": "b.py", "layer": "generated"}], "edges": [], "facts": {"unresolved_imports": []}, "metrics": {"node_count": 2, "edge_count": 0, "static_cycles": []}}
    report = audit(graph)
    assert report["integrity_pass"] is False
    assert report["identity_integrity_pass"] is False
    assert report["identity_collision_count"] == 1
    decision = decide(graph=graph, impact={"changed_files": []}, completeness=report)
    assert decision["decision"]["architecture_disposition"] == "blocked"
    assert decision["decision"]["dimensions"]["identity_integrity"] == "blocked"


def test_unresolved_reference_classes_are_preserved():
    graph = {"nodes": [{"id": "py:a", "type": "python_module", "source": "a.py", "layer": "generated"}], "edges": [], "facts": {"unresolved_imports": [{"specifier": "chrome:settings", "from": "a.py"}, {"specifier": ".local", "from": "a.py"}, {"specifier": "mystery_pkg", "from": "a.py"}]}, "metrics": {"node_count": 1, "edge_count": 0, "static_cycles": []}}
    classes = audit(graph)["residuals"]["unresolved_import_classes"]
    assert classes == {"relative_internal_reference": 1, "unresolved_absolute_reference": 1, "url_or_scheme": 1}


def test_disposition_separates_propositions(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "main.py").write_text("import unknown_package\n")
    graph = build_graph(subject=tmp_path)
    report = audit(graph, subject=tmp_path)
    decision = decide(graph=graph, impact={"changed_files": []}, completeness=report)
    dims = decision["decision"]["dimensions"]
    assert dims["artifact_integrity"] == "passed"
    assert dims["identity_integrity"] == "passed"
    assert dims["structural_coverage"] == "gaps-visible"
    assert dims["change_evidence"] == "not-requested"
    assert decision["decision"]["architecture_disposition"] == "review-required"
