"""Write the 1devteam.com reconstruction pack. Not a plan. Not Ajenda CI."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from graft_plus.ingest import IngestResult, IngestedFile, enrich, walk_subject

PACK_SCHEMA = "graft-pack-1"


def _fence(path: str) -> str:
    if path.endswith(".py"):
        return "python"
    if path.endswith((".ts", ".tsx")):
        return "ts"
    if path.endswith((".js", ".jsx", ".mjs")):
        return "js"
    if path.endswith(".json"):
        return "json"
    if path.endswith((".yml", ".yaml")):
        return "yaml"
    if path.endswith(".md"):
        return "markdown"
    return ""


def _readme(files: list[IngestedFile]) -> str | None:
    readmes = [f for f in files if re.match(r"readme(\.|$)", f.path.split("/")[-1], re.I)]
    if not readmes:
        return None
    readmes.sort(key=lambda f: (f.path.count("/"), f.path))
    body = "\n".join(line.rstrip() for line in readmes[0].content.splitlines()[:24])
    return body[:1200] or None


def _package_root(specifier: str) -> str:
    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split(".")[0]


def _repo_slug(ingest: IngestResult) -> tuple[str, str]:
    url = ingest.repo or "local"
    owner_repo = url
    if "github.com" in url:
        path = urlparse(url.replace("git@", "https://").replace(":", "/", 1) if url.startswith("git@") else url).path
        path = path.removesuffix(".git").strip("/")
        owner_repo = path or url
    sha = (ingest.sha or "HEAD")[:8]
    slug = re.sub(r"[^\w.-]+", "-", owner_repo) + f"-{sha}"
    return owner_repo, slug


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_pack(*, subject: Path, out: Path, graph: dict[str, Any], decision: dict[str, Any]) -> dict[str, str]:
    ingest = enrich(walk_subject(subject))
    repo, slug = _repo_slug(ingest)
    unresolved_map: dict[str, list[str]] = {}
    for spec, src in ingest.unresolved:
        unresolved_map.setdefault(spec, []).append(src)
    unresolved_rows = [{"specifier": k, "from": sorted(set(v))} for k, v in sorted(unresolved_map.items())]
    package_roots = sorted({_package_root(r["specifier"]) for r in unresolved_rows})
    disposition = decision.get("decision", {}).get("architecture_disposition", "clear")
    fingerprint = _fingerprint({"schema": PACK_SCHEMA, "files": [f.path for f in ingest.files], "sha": ingest.sha})
    negatives = [
        "This pack is a map. It is not a plan.",
        "implementsPlan is false.",
        "mergeAuthorization is not-determined even when disposition is clear.",
        "An acknowledgement is not a repair.",
        "Unresolved imports are facts, not missing files.",
        "Do not invent overlay (policy, saga, ownership, runtime authority) unless evidenced here.",
        "G.R.A.F.T.+ does not replace Ajenda execution and is not Ajenda's merge gate.",
    ]
    pack_obj = {
        "schema": PACK_SCHEMA,
        "product": "G.R.A.F.T.+",
        "package": "graft_plus",
        "role": "fact-substrate",
        "implementsPlan": False,
        "mergeAuthorization": "not-determined",
        "grants_execution_authority": False,
        "disposition": disposition,
        "fingerprint": fingerprint,
        "origin": {
            "kind": "folder",
            "url": ingest.repo,
            "ref": ingest.ref,
            "sha": ingest.sha,
            "skippedRoots": ingest.skipped_roots,
            "omittedNotes": ingest.omitted_notes,
            "recentCommits": ingest.commits,
            "readOnly": True,
        },
        "provenance": {"repo": repo, "ref": ingest.ref, "sha": ingest.sha, "capturedAt": ingest.captured_at},
        "reconstruction": {
            "files": len(ingest.files),
            "contracts": len(ingest.contracts),
            "inner_dependencies": len(ingest.inner),
            "unresolved": len(ingest.unresolved),
            "routes": len(ingest.routes),
            "omitted": len(ingest.omitted_notes),
        },
        "graph": {
            "node_count": graph.get("metrics", {}).get("node_count"),
            "edge_count": graph.get("metrics", {}).get("edge_count"),
        },
        "decision": decision.get("decision"),
        "facts": {
            "contracts": ingest.contracts,
            "inner": ingest.inner,
            "unresolved": unresolved_rows,
            "routes": ingest.routes,
            "negatives": negatives,
        },
        "files": [{"path": f.path, "language": f.language, "size": f.size} for f in ingest.files],
    }
    markdown = _map_md(
        ingest=ingest,
        repo=repo,
        slug=slug,
        disposition=disposition,
        fingerprint=fingerprint,
        unresolved_rows=unresolved_rows,
        package_roots=package_roots,
        negatives=negatives,
        graph=graph,
    )
    json_text = json.dumps(pack_obj, indent=2, sort_keys=True) + "\n"
    out.mkdir(parents=True, exist_ok=True)
    (out / "GRAFT-MAP.md").write_text(markdown, encoding="utf-8")
    (out / "GRAFT-PACK.json").write_text(json_text, encoding="utf-8")
    (out / "graph-architecture-decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    zip_name = f"GRAFT-PACK-{slug}.zip"
    zip_path = out / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GRAFT-MAP.md", markdown)
        zf.writestr("GRAFT-PACK.json", json_text)
        zf.writestr("graph-architecture-decision.json", json.dumps(decision, indent=2, sort_keys=True) + "\n")
        for item in ingest.files:
            zf.writestr(f"tree/{item.path}", item.content)
    return {"map": str(out / "GRAFT-MAP.md"), "json": str(out / "GRAFT-PACK.json"), "zip": str(zip_path)}


def _map_md(
    *,
    ingest: IngestResult,
    repo: str,
    slug: str,
    disposition: str,
    fingerprint: str,
    unresolved_rows: list[dict],
    package_roots: list[str],
    negatives: list[str],
    graph: dict[str, Any],
) -> str:
    readme = _readme(ingest.files)
    lines = [
        "# G.R.A.F.T.+ reconstruction map",
        "",
        "Product: G.R.A.F.T.+",
        "Role: fact-substrate",
        "Artifact: one pack for one revision (this markdown plus GRAFT-PACK.json and tree/)",
        f"Schema: {PACK_SCHEMA}",
        "implementsPlan: false",
        "mergeAuthorization: not-determined",
        f"Disposition: {disposition}",
        f"Fingerprint: {fingerprint}",
        f"Download-name: GRAFT-PACK-{slug}.zip",
        "",
        "## How to read this",
        "You are reading a reconstruction of one git revision. This is a map, not a plan and not a merge.",
        "Joints come first. Source for ingested files follows under Files. Answer follow-ups from this pack. Do not guess.",
        "An import not resolved in this tree is still a fact. It is not a missing file and not overlay.",
        "Do not invent overlay unless it is evidenced here. Honor negatives.",
        "If this markdown is truncated, open GRAFT-PACK.json and tree/ in the same zip.",
        "This pack replaces the 1devteam.com snapshot ingest. It is not Ajenda's execution gate.",
        "",
        "## Provenance",
        f"- Repository: {repo}",
        f"- Ref: {ingest.ref or 'unpinned'}",
        f"- SHA: {ingest.sha or 'unpinned'}",
        f"- Captured: {ingest.captured_at}",
        "- Read-only: yes",
        "",
        "## Recent commits",
    ]
    lines.extend([f"- {c}" for c in ingest.commits] or ["- none captured"])
    lines += ["", "## README (claimed intent)", readme or "- none in ingested files", "", "## Reconstruction"]
    metrics = graph.get("metrics") or {}
    lines += [
        f"- Files ingested: {len(ingest.files)}",
        f"- Graph nodes: {metrics.get('node_count', 0)}",
        f"- Graph edges: {metrics.get('edge_count', 0)}",
        f"- Contracts: {len(ingest.contracts)}",
        f"- Inner dependencies: {len(ingest.inner)}",
        f"- Unresolved imports: {len(ingest.unresolved)}",
        f"- Routes: {len(ingest.routes)}",
        f"- Readable files not ingested: {len(ingest.omitted_notes)}",
        "",
        "## Not ingested",
    ]
    lines.extend([f"- {n}" for n in ingest.omitted_notes] or ["- none"])
    lines += ["", "## Skipped directories"]
    lines.extend([f"- {n}" for n in ingest.skipped_roots] or ["- none"])
    lines += ["", "## Unresolved package roots"]
    lines.extend([f"- {n}" for n in package_roots] or ["- none"])
    lines += ["", "## Unresolved imports (not in this tree)"]
    lines.extend([f"- {r['specifier']} · from {', '.join(r['from'])}" for r in unresolved_rows] or ["- none"])
    lines += ["", "## Inventory (every ingested path)"]
    lines.extend([f"- {f.path}" for f in ingest.files] or ["- none"])
    lines += ["", "## Contracts"]
    lines.extend([f"- {c}" for c in ingest.contracts] or ["- none"])
    lines += ["", "## Routes"]
    lines.extend([f"- {r}" for r in ingest.routes] or ["- none"])
    lines += ["", "## Dependencies"]
    lines.extend([f"- {d}" for d in ingest.inner] or ["- none"])
    lines += ["", "## Docker"]
    lines.extend([f"- {p}" for p in ingest.docker] or ["- none in ingested files"])
    lines += ["", "## CI"]
    lines.extend([f"- {p}" for p in ingest.ci] or ["- none in ingested files"])
    lines += [
        "",
        "## Overlay",
        "- none. Overlay is residual until a reviewed relationship is attached.",
        "",
        "## Negatives (do not invent past these)",
    ]
    lines.extend([f"- {n}" for n in negatives])
    lines += ["", "## Files", "Every ingested file follows. Contracts and dependencies sit above its source.", ""]
    by_inner = {}
    for dep in ingest.inner:
        src = dep.split(" → ", 1)[0]
        by_inner.setdefault(src, []).append(dep)
    for item in ingest.files:
        fence = _fence(item.path)
        file_contracts = [c for c in ingest.contracts if c.startswith(item.path + " ")]
        lines.append(f"### {item.path}")
        lines.append("Contracts:")
        lines.extend([f"- {c}" for c in file_contracts] or ["- none declared"])
        lines.append("Dependencies:")
        lines.extend([f"- {d}" for d in by_inner.get(item.path, [])] or ["- none"])
        lines.append("Source:")
        lines.append("```" + fence)
        lines.append(item.content.rstrip("\n"))
        lines.append("```")
        lines.append("")
    lines += [
        "## Note",
        "These facts are the map. G.R.A.F.T.+ does not choose corrections, additions, or merge authority.",
        "",
    ]
    return "\n".join(lines)
