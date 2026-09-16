from pathlib import Path

from graft_plus.cli import reconstruct
from graft_plus.decision import decide
from graft_plus.graph import build_graph
from graft_plus.completeness import audit
from graft_plus.impact import analyze_impact

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_subject"


def test_tiny_subject_names_modules_and_tests():
    graph = build_graph(subject=FIXTURE)
    ids = {n["id"] for n in graph["nodes"]}
    assert "py:pkg.core" in ids
    assert "py:pkg" in ids
    assert any(i.startswith("test:") for i in ids)
    assert any(e["type"] == "imports" for e in graph["edges"])
    assert any(e["type"] == "tests" for e in graph["edges"])


def test_decision_never_grants_merge(tmp_path):
    graph = build_graph(subject=FIXTURE)
    completeness = audit(graph)
    impact = analyze_impact(graph, [])
    decision = decide(graph=graph, impact=impact, completeness=completeness)
    assert decision["decision"]["merge_authorization"] == "not-determined"
    assert decision["grants_execution_authority"] is False
    assert decision["implementsPlan"] is False
    assert decision["decision"]["full_ci_required"] is True


def test_cli_writes_decipher_pack(tmp_path):
    out = tmp_path / "pack"
    rc = reconstruct(FIXTURE, out, None, None, None)
    assert rc == 0
    assert (out / "graph-architecture-decision.json").exists()
    assert (out / "dependency-graph.v1.json").exists()


def test_frozen_negatives_cannot_grant_authority():
    graph = build_graph(subject=FIXTURE)
    completeness = audit(graph)
    completeness = {**completeness, "integrity_pass": True, "unacknowledged_blocking_findings": []}
    impact = analyze_impact(graph, [])
    decision = decide(graph=graph, impact=impact, completeness=completeness)
    assert decision["decision"]["architecture_disposition"] == "clear"
    assert decision["decision"]["merge_authorization"] == "not-determined"
    assert decision["grants_execution_authority"] is False


def test_pack_replaces_site_snapshot(tmp_path):
    import json, zipfile
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    assert (out / "GRAFT-MAP.md").exists()
    assert (out / "GRAFT-PACK.json").exists()
    payload = json.loads((out / "GRAFT-PACK.json").read_text())
    assert payload["schema"] == "graft-pack-1"
    assert payload["implementsPlan"] is False
    assert payload["mergeAuthorization"] == "not-determined"
    text = (out / "GRAFT-MAP.md").read_text()
    assert "How to read this" in text
    assert "not a plan" in text.lower()
    zips = list(out.glob("GRAFT-PACK-*.zip"))
    assert zips
    with zipfile.ZipFile(zips[0]) as zf:
        names = zf.namelist()
    assert "GRAFT-MAP.md" in names
    assert "GRAFT-PACK.json" in names
    assert any(n.startswith("tree/") for n in names)
