from pathlib import Path

from graft_plus.cli import reconstruct
from graft_plus.graph import build_graph

LIVE = Path(__file__).resolve().parents[1] / "src" / "graft_plus"
ORIGIN = Path(__file__).resolve().parents[1] / "docs" / "origin" / "ajenda_graph"
FIXTURE = Path(__file__).parent / "fixtures" / "tiny_subject"


def test_live_engine_does_not_contain_ajenda_catalogs():
    blob = ""
    for path in LIVE.rglob("*.py"):
        blob += path.read_text(encoding="utf-8")
    assert "job_catalog.py" not in blob
    assert "hubspot" not in blob.lower()
    assert "tenant-isolation-proof" not in blob
    assert "ajenda_bind" not in blob
    assert "ajenda_graph" not in blob


def test_origin_copy_is_archived_not_imported():
    assert (ORIGIN / "build_dependency_graph.py").exists()
    assert (ORIGIN / "SOURCE.txt").exists()


def test_universal_cli_does_not_block_on_missing_overlay(tmp_path):
    out = tmp_path / "pack"
    rc = reconstruct(FIXTURE, out, None, None, None)
    assert rc == 0
    graph = build_graph(subject=FIXTURE)
    types = {n["type"] for n in graph["nodes"]}
    assert "business_job" not in types
    assert "runtime_action" not in types
