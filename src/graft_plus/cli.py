"""CLI: reconstruct a subject into a decipher pack."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from graft_plus.completeness import audit
from graft_plus.decision import decide
from graft_plus.graph import build_graph
from graft_plus.impact import analyze_impact, changed_files


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_sha(subject: Path) -> str | None:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=subject, text=True, capture_output=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def reconstruct(subject: Path, out: Path, overlay: Path | None, base_ref: str | None, head_ref: str | None) -> int:
    graph = build_graph(subject=subject, overlay_path=overlay)
    completeness = audit(graph)
    impact = {
        "schema_version": "1.0",
        "changed_files": [],
        "changed_nodes": [],
        "unmapped_changed_files": [],
        "impacted_tests": [],
        "changed_node_count": 0,
        "changed_file_count": 0,
        "unmapped_changed_file_count": 0,
        "impacted_test_count": 0,
        "note": "no git range requested",
    }
    if base_ref and head_ref:
        impact = analyze_impact(graph, changed_files(subject, base_ref, head_ref))
    decision = decide(graph=graph, impact=impact, completeness=completeness)
    _write(out / "dependency-graph.v1.json", graph)
    _write(out / "graph-completeness-report.json", completeness)
    _write(out / "graph-impact-report.json", impact)
    _write(out / "graph-architecture-decision.json", decision)
    receipt = {
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "subject": str(subject),
        "subject_sha": _git_sha(subject),
        "status": "passed" if completeness.get("integrity_pass") else "failed",
        "decipher": "graph-architecture-decision.json",
        "grants_execution_authority": False,
        "implementsPlan": False,
        "merge_authorization": "not-determined",
    }
    _write(out / "graft-plus-gate.json", receipt)
    print(f"G.R.A.F.T.+ {receipt['status']}: {decision['decision']['architecture_disposition']}")
    print(f"Decipher: {out / 'graph-architecture-decision.json'}")
    print(f"Graph: {graph['metrics']['node_count']} nodes, {graph['metrics']['edge_count']} edges")
    return 0 if receipt["status"] == "passed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G.R.A.F.T.+ reconstruction map for AI review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("reconstruct", help="Build the decipher pack for a subject tree")
    rec.add_argument("--subject", type=Path, default=Path("."), help="Subject repository root")
    rec.add_argument("--out", type=Path, default=Path("artifacts/graft-pack"))
    rec.add_argument("--overlay", type=Path, default=None)
    rec.add_argument("--base-ref", default=None)
    rec.add_argument("--head-ref", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "reconstruct":
        return reconstruct(args.subject.resolve(), args.out, args.overlay, args.base_ref, args.head_ref)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
