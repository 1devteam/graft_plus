"""Walk one revision. Facts only. Not a plan."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    ".turbo",
    ".cache",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "*.egg-info",
}
SKIP_FILE_NAMES = {".env", ".env.local", ".env.production"}
MAX_TEXT_BYTES = 2 * 1024 * 1024
FRONTEND_IMPORT_RE = re.compile(r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]")
PY_FROM_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z0-9_\.]+)", re.M)


@dataclass
class IngestedFile:
    path: str
    content: str
    language: str
    size: int


@dataclass
class IngestResult:
    files: list[IngestedFile]
    skipped_roots: list[str]
    omitted_notes: list[str]
    captured_at: str
    sha: str | None
    ref: str | None
    repo: str | None
    commits: list[str]
    unresolved: list[tuple[str, str]]  # specifier, from_path
    contracts: list[str]
    inner: list[str]
    routes: list[str]
    docker: list[str]
    ci: list[str]


def _lang(path: str) -> str:
    if path.endswith(".py"):
        return "python"
    if path.endswith((".ts", ".tsx")):
        return "typescript"
    if path.endswith((".js", ".jsx", ".mjs")):
        return "javascript"
    if path.endswith(".go"):
        return "go"
    if path.endswith(".rs"):
        return "rust"
    if path.endswith((".md", ".rst")):
        return "markdown"
    if path.endswith((".yml", ".yaml")):
        return "yaml"
    if path.endswith(".json"):
        return "json"
    return "other"


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


def walk_subject(subject: Path) -> IngestResult:
    subject = subject.resolve()
    files: list[IngestedFile] = []
    skipped: set[str] = set()
    omitted: list[str] = []
    for path in sorted(subject.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(subject).parts
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel_parts):
            skipped.add(next(p for p in rel_parts if p in SKIP_DIRS or p.endswith(".egg-info")))
            continue
        if path.name in SKIP_FILE_NAMES or path.name.startswith(".env."):
            omitted.append(f"{path.relative_to(subject).as_posix()} (env)")
            continue
        rel = path.relative_to(subject).as_posix()
        try:
            data = path.read_bytes()
        except OSError as exc:
            omitted.append(f"{rel} (unreadable: {exc})")
            continue
        if _is_binary(data):
            omitted.append(f"{rel} (binary)")
            continue
        if len(data) > MAX_TEXT_BYTES:
            omitted.append(f"{rel} (oversize)")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            omitted.append(f"{rel} (unreadable)")
            continue
        files.append(IngestedFile(path=rel, content=text, language=_lang(rel), size=len(data)))
    return IngestResult(
        files=files,
        skipped_roots=sorted(skipped),
        omitted_notes=omitted,
        captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sha=_git(subject, ["rev-parse", "HEAD"]),
        ref=_git(subject, ["rev-parse", "--abbrev-ref", "HEAD"]),
        repo=_git(subject, ["config", "--get", "remote.origin.url"]),
        commits=_commits(subject),
        unresolved=[],
        contracts=[],
        inner=[],
        routes=[],
        docker=[],
        ci=[],
    )


def _git(subject: Path, args: list[str]) -> str | None:
    import subprocess

    r = subprocess.run(["git", *args], cwd=subject, text=True, capture_output=True, check=False)
    out = r.stdout.strip()
    return out if r.returncode == 0 and out else None


def _commits(subject: Path) -> list[str]:
    import subprocess

    r = subprocess.run(
        ["git", "log", "-8", "--pretty=format:%h %s"],
        cwd=subject,
        text=True,
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line.strip()]


def enrich(ingest: IngestResult) -> IngestResult:
    by_path = {f.path for f in ingest.files}
    unresolved: list[tuple[str, str]] = []
    contracts: list[str] = []
    inner: list[str] = []
    routes: list[str] = []
    for item in ingest.files:
        if item.language == "python":
            contracts.extend(_py_contracts(item))
            for spec, resolved in _py_imports(item, by_path):
                if resolved:
                    inner.append(f"{item.path} → {resolved}")
                else:
                    unresolved.append((spec, item.path))
            routes.extend(_py_routes(item))
        elif item.language in {"typescript", "javascript"}:
            contracts.extend(_ts_contracts(item))
            for spec, resolved in _ts_imports(item, by_path):
                if resolved:
                    inner.append(f"{item.path} → {resolved}")
                else:
                    unresolved.append((spec, item.path))
    ingest.unresolved = unresolved
    ingest.contracts = contracts
    ingest.inner = inner
    ingest.routes = routes
    ingest.docker = [f.path for f in ingest.files if "Dockerfile" in f.path or "docker-compose" in f.path]
    ingest.ci = [f.path for f in ingest.files if ".github/workflows" in f.path or "gitlab-ci" in f.path]
    return ingest


def _py_contracts(item: IngestedFile) -> list[str]:
    try:
        tree = ast.parse(item.content)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.append(f"{item.path} function {node.name}")
        elif isinstance(node, ast.ClassDef):
            out.append(f"{item.path} class {node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            out.append(f"{item.path} function {node.name}")
    return out


def _py_imports(item: IngestedFile, files: set[str]) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    try:
        tree = ast.parse(item.content)
    except SyntaxError:
        return rows
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append((alias.name, _resolve_mod(alias.name, files)))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            rows.append((node.module, _resolve_mod(node.module, files)))
    return rows


def _resolve_mod(module: str, files: set[str]) -> str | None:
    rel = module.replace(".", "/")
    for cand in (f"{rel}.py", f"{rel}/__init__.py", f"src/{rel}.py", f"src/{rel}/__init__.py"):
        if cand in files:
            return cand
    return None


def _py_routes(item: IngestedFile) -> list[str]:
    found: list[str] = []
    for i, line in enumerate(item.content.splitlines(), 1):
        m = re.search(r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", line)
        if m:
            found.append(f"{m.group(1).upper()} {m.group(2)} · {item.path}:{i}")
    return found


def _ts_contracts(item: IngestedFile) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"export\s+(?:async\s+)?function\s+(\w+)", item.content):
        out.append(f"{item.path} function {m.group(1)}")
    for m in re.finditer(r"export\s+(?:default\s+)?class\s+(\w+)", item.content):
        out.append(f"{item.path} class {m.group(1)}")
    return out


def _ts_imports(item: IngestedFile, files: set[str]) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    parent = str(Path(item.path).parent)
    for m in FRONTEND_IMPORT_RE.finditer(item.content):
        spec = m.group(1)
        if spec.startswith("."):
            raw = str((Path(parent) / spec).as_posix())
            while raw.startswith("./"):
                raw = raw[2:]
            cands = [raw, raw + ".ts", raw + ".tsx", raw + "/index.ts"]
            hit = next((c for c in cands if c in files), None)
            rows.append((spec, hit))
        else:
            rows.append((spec, None))
    return rows
