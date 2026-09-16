"""Materialize a public git subject. No product-domain rules."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

_GITHUB = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$",
    re.I,
)
_OWNER_REPO = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)$")


def parse_public_repo(spec: str) -> tuple[str, str]:
    raw = spec.strip()
    match = _GITHUB.match(raw.rstrip("/")) or _OWNER_REPO.match(raw)
    if match is None:
        raise ValueError("expected owner/repo or a public github.com URL")
    owner, repo = match.group("owner"), match.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def clone_public_repo(spec: str, dest: Path | None = None, ref: str | None = None) -> Path:
    owner, repo = parse_public_repo(spec)
    url = f"https://github.com/{owner}/{repo}.git"
    root = dest or Path(tempfile.mkdtemp(prefix=f"graft-{owner}-{repo}-"))
    root.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([url, str(root)])
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"unable to clone {url}")
    return root
