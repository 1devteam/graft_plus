from __future__ import annotations

import subprocess

import pytest

from graft_plus.change_set import build_change_set


def _git(path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_change_set_is_direct_only_and_resolves_exact_shas(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "graft@example.test")
    _git(tmp_path, "config", "user.name", "GRAFT Test")

    (tmp_path / "a.py").write_text("VALUE = 1\n")
    (tmp_path / "unmapped.txt").write_text("before\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    (tmp_path / "a.py").write_text("VALUE = 2\n")
    (tmp_path / "unmapped.txt").write_text("after\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "head")
    head = _git(tmp_path, "rev-parse", "HEAD")

    graph = {
        "nodes": [
            {"id": "py:a", "type": "python_module", "source": "a.py"},
            {"id": "py:b", "type": "python_module", "source": "b.py"},
        ],
        "edges": [
            {"from": "py:b", "to": "py:a", "type": "imports"},
        ],
    }

    change_set = build_change_set(graph, tmp_path, base, head)

    assert change_set["requested"] is True
    assert change_set["base_sha"] == base
    assert change_set["head_sha"] == head
    assert change_set["changed_files"] == ["a.py", "unmapped.txt"]
    assert change_set["direct_node_mappings"] == [
        {"source": "a.py", "node_ids": ["py:a"]},
    ]
    assert change_set["changed_node_ids"] == ["py:a"]
    assert change_set["unmapped_changed_files"] == ["unmapped.txt"]

    serialized = str(change_set).lower()
    for forbidden in (
        "upstream_consumers",
        "downstream_dependencies",
        "impacted_tests",
        "proof",
        "risk",
        "architecture_disposition",
    ):
        assert forbidden not in serialized


def test_change_set_without_range_is_explicitly_empty(tmp_path):
    graph = {"nodes": [], "edges": []}
    change_set = build_change_set(graph, tmp_path, None, None)

    assert change_set["requested"] is False
    assert change_set["changed_files"] == []
    assert change_set["changed_node_ids"] == []
    assert change_set["unmapped_changed_files"] == []


def test_change_set_requires_complete_ref_pair(tmp_path):
    graph = {"nodes": [], "edges": []}
    with pytest.raises(ValueError, match="must be provided together"):
        build_change_set(graph, tmp_path, "main", None)
