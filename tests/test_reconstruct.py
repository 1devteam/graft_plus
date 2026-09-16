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

def test_artifact_is_reconstruction_not_source_dump(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    names = {p.name for p in out.iterdir()}
    assert "graph-architecture-decision.json" in names
    assert "dependency-graph.v1.json" in names
    assert "graph-completeness-report.json" in names
    assert "graph-impact-report.json" in names
    assert "graft-plus-receipt.json" in names
    assert "GRAFT-MAP.md" not in names
    assert "GRAFT-PACK.json" not in names
    assert not list(out.glob("*.zip"))
    assert not (out / "tree").exists()


def test_public_repo_parse():
    from graft_plus.fetch import parse_public_repo
    assert parse_public_repo("octocat/Hello-World") == ("octocat", "Hello-World")
    assert parse_public_repo("https://github.com/octocat/Hello-World") == ("octocat", "Hello-World")


def test_proof_has_no_ajenda_bundles():
    from graft_plus.proof import select_proofs
    src = Path(__file__).resolve().parents[1] / "src"
    text = (src / "graft_plus" / "proof.py").read_text()
    assert "tenant-isolation" not in text
    assert "hubspot" not in text.lower()
    assert "ajenda" not in text.lower()
    manifest = select_proofs({"impacted_tests": ["test:tests/test_reconstruct.py"], "changed_node_count": 1}, {})
    assert manifest["required_tests"] == ["test:tests/test_reconstruct.py"]
    assert manifest["selected_bundles"] == []


def test_cli_writes_proof_manifest(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    names = {p.name for p in out.iterdir()}
    assert "graph-proof-manifest.json" in names
    assert "graph-architecture-decision.json" in names
    assert "GRAFT-MAP.md" not in names
