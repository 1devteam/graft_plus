"""Bind the copied Ajenda graph scripts to a subject. Scripts stay as-is."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

GRAPH_DIR = Path(__file__).resolve().parent / "ajenda_graph"
EMPTY_OVERLAY = GRAPH_DIR / "_empty_overlay.json"


def _ensure_path() -> None:
    path = str(GRAPH_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)


def bind(subject: Path) -> Any:
    """Point the Ajenda modules at subject. Returns build_dependency_graph module."""

    subject = subject.resolve()
    _ensure_path()
    import build_dependency_graph as bdg

    bdg.REPO_ROOT = subject
    overlay = subject / "docs" / "contracts" / "dependency-graph.overlay.v1.json"
    if overlay.exists():
        bdg.OVERLAY_PATH = overlay
    else:
        dest = subject / ".graft-plus-empty-overlay.json"
        dest.write_text(EMPTY_OVERLAY.read_text(encoding="utf-8"), encoding="utf-8")
        bdg.OVERLAY_PATH = dest
    bdg.DEFAULT_OUTPUT = subject / "docs" / "architecture" / "dependency-graph.v1.json"
    bdg.PRODUCTION_PYTHON_ROOTS = (subject / "backend", subject / "services")
    bdg.GRAPH_TOOLING_PYTHON_ROOT = subject / "scripts" / "validation"
    bdg.GRAPH_TOOLING_WORKFLOW_ROOT = subject / ".github" / "workflows"

    import graph_runtime_contract_inventory as rci
    import graph_runtime_action_selection_inventory as rasi

    def _empty_contract(_repo: Path) -> dict[str, Any]:
        return {"nodes": [], "edges": [], "findings": [], "metrics": {}}

    def _empty_actions(_repo: Path) -> dict[str, Any]:
        return {"action_nodes": [], "nodes": [], "edges": [], "findings": [], "metrics": {}}

    orig_contract = rci.collect_runtime_contract_inventory
    orig_actions = rasi.collect_runtime_action_selection_inventory

    def contract(repo_root: Path) -> dict[str, Any]:
        if not (repo_root / rci.JOB_CATALOG_PATH).exists():
            return _empty_contract(repo_root)
        return orig_contract(repo_root)

    def actions(repo_root: Path) -> dict[str, Any]:
        if not (repo_root / rasi.JOB_CATALOG_PATH).exists():
            return _empty_actions(repo_root)
        return orig_actions(repo_root)

    rci.collect_runtime_contract_inventory = contract
    rasi.collect_runtime_action_selection_inventory = actions
    bdg.collect_runtime_contract_inventory = contract
    bdg.collect_runtime_action_selection_inventory = actions

    import pr_invariant_classifier as pic

    pic.REPO_ROOT = subject

    import graph_selective_ci as gsc

    gsc.REPO_ROOT = subject

    for name in (
        "graph_completeness_audit",
        "graph_impact_analysis",
        "graph_proof_selection",
        "graph_architecture_decision",
    ):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)

    return bdg


def reconstruct_with_ajenda(
    subject: Path,
    out: Path,
    base_ref: str | None,
    head_ref: str | None,
) -> dict[str, Any]:
    """Run the copied Ajenda pipeline against subject and write the pack."""

    subject = subject.resolve()
    bdg = bind(subject)
    graph = bdg.build_graph()

    from graph_completeness_audit import audit_graph
    from graph_impact_analysis import analyze_impact
    from graph_proof_selection import select_proofs
    from graph_architecture_decision import build_decision_manifest
    from pr_invariant_classifier import _discover_changes

    if base_ref and head_ref:
        changed, _ = _discover_changes(base_ref, head_ref)
        impact = analyze_impact(graph, changed)
    else:
        impact = analyze_impact(graph, [])
        impact["note"] = "no git range requested; blast-radius fields are present"

    completeness = audit_graph(graph)
    proofs = select_proofs(impact)
    decision = build_decision_manifest(impact, proofs, completeness)
    decision.setdefault("product", "G.R.A.F.T.+")
    decision.setdefault("package", "graft_plus")
    decision.setdefault("role", "fact-substrate")
    decision.setdefault("grants_execution_authority", False)
    decision.setdefault("implementsPlan", False)
    decision["decision"]["merge_authorization"] = "not-determined"

    out.mkdir(parents=True, exist_ok=True)

    def write(name: str, payload: dict[str, Any]) -> None:
        (out / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write("dependency-graph.v1.json", graph)
    write("graph-completeness-report.json", completeness)
    write("graph-impact-report.json", impact)
    write("graph-proof-manifest.json", proofs)
    write("graph-architecture-decision.json", decision)
    return {
        "graph": graph,
        "impact": impact,
        "completeness": completeness,
        "proofs": proofs,
        "decision": decision,
    }
