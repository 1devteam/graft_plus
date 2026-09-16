"""Portable language adapters that feed the canonical graph shape."""

from __future__ import annotations

import re
from pathlib import Path

from graft_plus.graph_types import StaticEdge, StaticNode
from graft_plus.inventory import rel, skipped
from graft_plus.runtime import is_runtime

JAVASCRIPT_SUFFIXES = {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}
SHELL_SUFFIXES = {".bash", ".sh", ".zsh"}
JS_IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]"
    r"|\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)"
    r"|\bimport\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
SHELL_SOURCE_RE = re.compile(r"^\s*(?:source|\.)\s+['\"]?([^'\"\s;]+)", re.M)
BATS_LOAD_RE = re.compile(r"^\s*load\s+['\"]?([^'\"\s;]+)", re.M)
PYTHON_SCRIPT_RE = re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+['\"]?([^'\"\s;]+\.py)")
TEST_PATH_RE = re.compile(r"(?:^|/)(?:tests?|specs?|__tests__)(?:/|$)|(?:\.test|\.spec)\.[^.]+$", re.I)


def javascript_id(subject: Path, path: Path) -> str:
    return "js:" + rel(subject, path)


def shell_id(subject: Path, path: Path) -> str:
    return "sh:" + rel(subject, path)


def is_test_path(path_value: str, path: Path) -> bool:
    return path.suffix.lower() == ".bats" or bool(TEST_PATH_RE.search(path_value))


def _javascript_files(subject: Path) -> tuple[set[Path], set[Path]]:
    production: set[Path] = set()
    tests: set[Path] = set()
    for path in subject.rglob("*"):
        if not path.is_file() or skipped(subject, path) or path.suffix.lower() not in JAVASCRIPT_SUFFIXES:
            continue
        resolved = path.resolve()
        (tests if is_test_path(rel(subject, path), path) else production).add(resolved)
    return production, tests


def _resolve_js(source: Path, specifier: str, files: set[Path]) -> Path | None:
    if not specifier.startswith("."):
        return None
    raw = (source.parent / specifier).resolve()
    candidates = [raw]
    candidates.extend(raw.with_suffix(suffix) for suffix in sorted(JAVASCRIPT_SUFFIXES))
    candidates.extend(raw / f"index{suffix}" for suffix in sorted(JAVASCRIPT_SUFFIXES))
    return next((candidate for candidate in candidates if candidate in files), None)


def _js_specifiers(text: str) -> list[str]:
    return [next(value for value in match.groups() if value is not None) for match in JS_IMPORT_RE.finditer(text)]


def collect_javascript_graph(
    subject: Path,
) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    production, tests = _javascript_files(subject)
    all_files = production | tests
    nodes = [
        StaticNode(id=javascript_id(subject, path), type="javascript_module", source=rel(subject, path))
        for path in sorted(production)
    ]
    nodes.extend(
        StaticNode(id=f"test:{rel(subject, path)}", type="test_module", source=rel(subject, path))
        for path in sorted(tests)
    )
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path in sorted(all_files):
        path_value = rel(subject, path)
        source_id = f"test:{path_value}" if path in tests else javascript_id(subject, path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for specifier in _js_specifiers(text):
            target = _resolve_js(path, specifier, all_files)
            if target is not None and target != path:
                target_id = javascript_id(subject, target) if target in production else f"test:{rel(subject, target)}"
                edge_type = "tests" if path in tests and target in production else "imports"
                edges.add(StaticEdge(source=source_id, target=target_id, type=edge_type, evidence=path_value))
            elif specifier.startswith(".") or not is_runtime(specifier):
                unresolved.append({"specifier": specifier, "from": path_value})
    return nodes, sorted(edges, key=lambda item: (item.source, item.target, item.type)), unresolved


def _shell_files(subject: Path) -> tuple[set[Path], set[Path]]:
    production: set[Path] = set()
    tests: set[Path] = set()
    for path in subject.rglob("*"):
        if not path.is_file() or skipped(subject, path):
            continue
        path_value = rel(subject, path)
        shell = path.suffix.lower() in SHELL_SUFFIXES or path.suffix.lower() == ".bats"
        if not shell and not path.suffix:
            try:
                first = path.open("rb").readline(256)
            except OSError:
                continue
            shell = first.startswith(b"#!") and any(name in first for name in (b"/sh", b"bash", b"zsh"))
        if not shell:
            continue
        resolved = path.resolve()
        (tests if is_test_path(path_value, path) else production).add(resolved)
    return production, tests


def _strip_shell_variable(value: str) -> str:
    value = value.strip().strip("'\"")
    value = re.sub(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/?", "", value)
    return value.removeprefix("./")


def _resolve_shell(subject: Path, source: Path, raw: str, files: set[Path]) -> Path | None:
    cleaned = _strip_shell_variable(raw)
    if not cleaned:
        return None
    direct = [(source.parent / cleaned).resolve(), (subject / cleaned).resolve()]
    direct.extend(candidate.with_suffix(suffix) for candidate in list(direct) if not candidate.suffix for suffix in SHELL_SUFFIXES)
    hit = next((candidate for candidate in direct if candidate in files), None)
    if hit is not None:
        return hit
    basename = Path(cleaned).name
    matches = sorted(path for path in files if path.name == basename or path.stem == basename)
    return matches[0] if len(matches) == 1 else None


def collect_shell_graph(
    subject: Path,
    python_by_source: dict[str, str],
) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    production, tests = _shell_files(subject)
    all_files = production | tests
    nodes = [
        StaticNode(id=shell_id(subject, path), type="shell_module", source=rel(subject, path))
        for path in sorted(production)
    ]
    nodes.extend(
        StaticNode(id=f"test:{rel(subject, path)}", type="test_module", source=rel(subject, path))
        for path in sorted(tests)
    )
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path in sorted(all_files):
        path_value = rel(subject, path)
        source_id = f"test:{path_value}" if path in tests else shell_id(subject, path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        references = [*SHELL_SOURCE_RE.findall(text), *BATS_LOAD_RE.findall(text)]
        for raw in references:
            target = _resolve_shell(subject, path, raw, all_files)
            if target is None:
                unresolved.append({"specifier": raw, "from": path_value})
                continue
            target_id = shell_id(subject, target) if target in production else f"test:{rel(subject, target)}"
            edge_type = "tests" if path in tests and target in production else "sources"
            edges.add(StaticEdge(source=source_id, target=target_id, type=edge_type, evidence=path_value))
        for raw in PYTHON_SCRIPT_RE.findall(text):
            cleaned = _strip_shell_variable(raw)
            candidates = [(path.parent / cleaned).resolve(), (subject / cleaned).resolve()]
            target_path = next((candidate for candidate in candidates if candidate.is_file()), None)
            if target_path is None:
                continue
            target = python_by_source.get(rel(subject, target_path))
            if target:
                edges.add(StaticEdge(source=source_id, target=target, type="invokes", evidence=path_value))
    return nodes, sorted(edges, key=lambda item: (item.source, item.target, item.type)), unresolved
