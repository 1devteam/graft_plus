from pathlib import Path

from graft_plus.ajenda_bind import GRAPH_DIR, reconstruct_with_ajenda
from graft_plus.cli import reconstruct

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_subject"
ORIGIN = [
    "build_dependency_graph.py",
    "graph_semantic_inventory.py",
    "graph_impact_analysis.py",
    "graph_proof_selection.py",
    "graph_completeness_audit.py",
    "graph_architecture_decision.py",
    "graph_function_inventory.py",
    "graph_runtime_contract_inventory.py",
    "graft_plus_gate.py",
]


def test_ajenda_scripts_are_present_as_copied():
    for name in ORIGIN:
        path = GRAPH_DIR / name
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert "Ajenda" in text or "canonical" in text or "graph" in text.lower()
    assert (GRAPH_DIR / "SOURCE.txt").read_text().startswith("Copied as-is")


def test_cli_uses_ajenda_pipeline(tmp_path):
    out = tmp_path / "pack"
    rc = reconstruct(FIXTURE, out, None, None, None)
    assert rc == 0
    decision = (out / "graph-architecture-decision.json").read_text()
    assert "not-determined" in decision
    assert (out / "dependency-graph.v1.json").exists()
    assert (out / "graph-completeness-report.json").exists()
    assert (out / "graph-impact-report.json").exists()
    assert (out / "graph-proof-manifest.json").exists()
