"""CLI: reconstruct a subject into a decipher pack using the Ajenda graph scripts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from graft_plus.ajenda_bind import reconstruct_with_ajenda
from graft_plus.fetch import clone_public_repo


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_sha(subject: Path) -> str | None:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=subject, text=True, capture_output=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def reconstruct(
    subject: Path,
    out: Path,
    overlay: Path | None,
    base_ref: str | None,
    head_ref: str | None,
) -> int:
    del overlay  # overlay is the subject's docs/contracts file; Ajenda scripts load it
    pack = reconstruct_with_ajenda(subject, out, base_ref, head_ref)
    graph = pack["graph"]
    completeness = pack["completeness"]
    decision = pack["decision"]
    integrity = (completeness.get("integrity") or {}).get("pass") is True
    blocking = (completeness.get("integrity") or {}).get("unacknowledged_blocking_findings") or []
    receipt = {
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "engine": "ajenda-graph-as-is",
        "subject": str(subject),
        "subject_sha": _git_sha(subject),
        "status": "passed" if integrity and not blocking else "failed",
        "decipher": "graph-architecture-decision.json",
        "files": [
            "graph-architecture-decision.json",
            "dependency-graph.v1.json",
            "graph-completeness-report.json",
            "graph-impact-report.json",
            "graph-proof-manifest.json",
            "graft-plus-receipt.json",
        ],
        "grants_execution_authority": False,
        "implementsPlan": False,
        "merge_authorization": "not-determined",
    }
    _write(out / "graft-plus-receipt.json", receipt)
    print(f"G.R.A.F.T.+ {receipt['status']}: {decision['decision']['architecture_disposition']}")
    print(f"Decipher: {out / 'graph-architecture-decision.json'}")
    print(f"Graph: {graph['metrics']['node_count']} nodes, {graph['metrics']['edge_count']} edges")
    return 0 if receipt["status"] == "passed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G.R.A.F.T.+ reconstruction map for AI review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("reconstruct", help="Build the decipher pack for a subject tree or public repo")
    rec.add_argument("--subject", type=Path, default=None, help="Local subject repository root")
    rec.add_argument("--repo", default=None, help="Public GitHub owner/repo or URL")
    rec.add_argument("--ref", default=None, help="Git ref when using --repo")
    rec.add_argument("--out", type=Path, default=Path("artifacts/graft-pack"))
    rec.add_argument("--overlay", type=Path, default=None)
    rec.add_argument("--base-ref", default=None)
    rec.add_argument("--head-ref", default=None)
    args = parser.parse_args(argv)
    if args.cmd != "reconstruct":
        return 2
    if args.subject and args.repo:
        parser.error("pass only one of --subject or --repo")
    if args.repo:
        subject = clone_public_repo(args.repo, ref=args.ref)
    else:
        subject = (args.subject or Path(".")).resolve()
    overlay = args.overlay
    if overlay is None:
        default_overlay = subject / "docs" / "contracts" / "dependency-graph.overlay.v1.json"
        overlay = default_overlay if default_overlay.exists() else None
    return reconstruct(subject, args.out, overlay, args.base_ref, args.head_ref)


if __name__ == "__main__":
    raise SystemExit(main())
