from graft_plus.completeness import audit
from graft_plus.graph import build_graph


def test_mock_patch_is_not_http_patch_route(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "worker.py").write_text(
        "from unittest import mock\n"
        "@mock.patch('subprocess.run')\n"
        "def execute(fake_run):\n"
        "    return fake_run\n"
    )

    graph = build_graph(subject=tmp_path)
    assert not any(
        node["type"] == "http_route" and node.get("method") == "PATCH"
        for node in graph["nodes"]
    )


def test_duplicate_canonical_identity_fails_instrument_integrity():
    graph = {
        "nodes": [
            {
                "id": "py:dup",
                "type": "python_module",
                "source": "a.py",
                "layer": "generated",
            },
            {
                "id": "py:dup",
                "type": "python_module",
                "source": "b.py",
                "layer": "generated",
            },
        ],
        "edges": [],
        "facts": {"unresolved_imports": []},
        "metrics": {"node_count": 2, "edge_count": 0, "static_cycles": []},
    }

    report = audit(graph)
    assert report["integrity_pass"] is False
    assert report["identity_integrity_pass"] is False
    assert report["identity_collision_count"] == 1
    assert "decision" not in report


def test_unresolved_reference_classes_are_preserved():
    graph = {
        "nodes": [
            {
                "id": "py:a",
                "type": "python_module",
                "source": "a.py",
                "layer": "generated",
            }
        ],
        "edges": [],
        "facts": {
            "unresolved_imports": [
                {"specifier": "chrome:settings", "from": "a.py"},
                {"specifier": ".local", "from": "a.py"},
                {"specifier": "mystery_pkg", "from": "a.py"},
            ]
        },
        "metrics": {"node_count": 1, "edge_count": 0, "static_cycles": []},
    }

    classes = audit(graph)["residuals"]["unresolved_import_classes"]
    assert classes == {
        "relative_internal_reference": 1,
        "unresolved_absolute_reference": 1,
        "url_or_scheme": 1,
    }


def test_structural_gaps_remain_visible_without_disposition(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "main.py").write_text("import unknown_package\n")

    graph = build_graph(subject=tmp_path)
    report = audit(graph, subject=tmp_path)

    assert report["integrity_pass"] is True
    assert report["identity_integrity_pass"] is True
    assert report["residuals"]["unresolved_import_count"] == 1
    assert report["residuals"]["unresolved_package_roots"] == ["unknown_package"]
    assert "architecture_disposition" not in str(report)
