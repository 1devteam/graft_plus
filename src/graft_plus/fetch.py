"""Materialize a public git subject. No product-domain rules."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_GITHUB = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$",
    re.I,
)
_OWNER_REPO = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class RepositoryLimitError(RuntimeError):
    """Raised when a materialized repository exceeds service safety limits."""


@dataclass(frozen=True, slots=True)
class CloneLimits:
    """Resource limits applied to an untrusted public repository checkout."""

    timeout_seconds: int = 60
    max_files: int = 20_000
    max_total_bytes: int = 100 * 1024 * 1024
    max_file_bytes: int = 5 * 1024 * 1024


def parse_public_repo(spec: str) -> tuple[str, str]:
    raw = spec.strip()
    match = _GITHUB.match(raw.rstrip("/")) or _OWNER_REPO.match(raw)
    if match is None:
        raise ValueError("expected owner/repo or a public github.com URL")
    owner, repo = match.group("owner"), match.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def validate_ref(ref: str) -> str:
    """Return a safe branch, tag, or commit-ish accepted as a git fetch ref."""
    value = ref.strip()
    if not _REF.fullmatch(value) or ".." in value or "//" in value or value.endswith(("/", ".lock")):
        raise ValueError("invalid git ref")
    return value


def validate_checkout(root: Path, limits: CloneLimits) -> None:
    """Reject unsafe links and repositories that exceed bounded service input."""
    count = 0
    total = 0
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            raise RepositoryLimitError(f"symbolic links are not supported: {path.relative_to(root)}")
        if not path.is_file():
            continue
        count += 1
        size = path.stat().st_size
        total += size
        if count > limits.max_files:
            raise RepositoryLimitError(f"repository exceeds {limits.max_files} files")
        if size > limits.max_file_bytes:
            raise RepositoryLimitError(f"file exceeds {limits.max_file_bytes} bytes: {path.relative_to(root)}")
        if total > limits.max_total_bytes:
            raise RepositoryLimitError(f"repository exceeds {limits.max_total_bytes} materialized bytes")


def _run_git(cmd: list[str], *, cwd: Path | None, timeout_seconds: int) -> None:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"git operation exceeded {timeout_seconds} seconds") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git command failed: {' '.join(cmd)}")


def clone_public_repo(
    spec: str,
    dest: Path | None = None,
    ref: str | None = None,
    *,
    limits: CloneLimits | None = None,
) -> Path:
    """Materialize one public repository revision within the service safety envelope.

    When ``ref`` is supplied, fetch it explicitly and detach at ``FETCH_HEAD`` so
    branch names, tags, and reachable commit SHAs share the same reproducible
    materialization path. Resource limits remain unchanged and are enforced after
    checkout.
    """

    owner, repo = parse_public_repo(spec)
    bounded = limits or CloneLimits()
    url = f"https://github.com/{owner}/{repo}.git"
    root = dest or Path(tempfile.mkdtemp(prefix=f"graft-{owner}-{repo}-"))

    if ref:
        revision = validate_ref(ref)
        root.mkdir(parents=True, exist_ok=True)
        _run_git(["git", "init"], cwd=root, timeout_seconds=bounded.timeout_seconds)
        _run_git(["git", "remote", "add", "origin", url], cwd=root, timeout_seconds=bounded.timeout_seconds)
        _run_git(
            ["git", "fetch", "--depth", "1", "origin", revision],
            cwd=root,
            timeout_seconds=bounded.timeout_seconds,
        )
        _run_git(
            ["git", "checkout", "--detach", "FETCH_HEAD"],
            cwd=root,
            timeout_seconds=bounded.timeout_seconds,
        )
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        _run_git(
            ["git", "clone", "--depth", "1", url, str(root)],
            cwd=None,
            timeout_seconds=bounded.timeout_seconds,
        )

    validate_checkout(root, bounded)
    return root
