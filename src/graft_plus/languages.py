"""Deterministic static adapters for additional common language families.

The adapters intentionally stop at source-visible declarations.  They resolve
only exact relative paths, exact declared symbols, or unambiguous repository
module names; build-system and runtime lookup behavior is not inferred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from graft_plus.graph_types import StaticEdge, StaticNode
from graft_plus.inventory import rel, skipped


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    name: str
    prefix: str
    node_type: str
    suffixes: frozenset[str]
    references: Callable[[str], list[tuple[str, str]]]


def _matches(pattern: str, text: str, *, flags: int = re.M) -> list[str]:
    return [match.group(1) for match in re.finditer(pattern, text, flags)]


def _ruby_references(text: str) -> list[tuple[str, str]]:
    local = _matches(r"^\s*require_relative\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    external = _matches(r"^\s*require\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    return [("relative", value) for value in local] + [("external", value) for value in external]


def _php_references(text: str) -> list[tuple[str, str]]:
    values = _matches(
        r"\b(?:include|include_once|require|require_once)\s*(?:\(\s*)?(?:__DIR__\s*\.\s*)?['\"]([^'\"]+)['\"]",
        text,
    )
    return [("relative", value) for value in values]


def _native_references(text: str) -> list[tuple[str, str]]:
    return [("relative", value) for value in _matches(r'^\s*#\s*include\s*"([^"]+)"', text)]


def _rust_references(text: str) -> list[tuple[str, str]]:
    modules = _matches(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", text)
    crate_uses = _matches(r"^\s*use\s+crate::([A-Za-z_][A-Za-z0-9_:]*)", text)
    external = _matches(r"^\s*(?:use|extern\s+crate)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    return (
        [("rust_mod", value) for value in modules]
        + [("rust_crate", value) for value in crate_uses]
        + [("external", value) for value in external if value not in {"alloc", "core", "crate", "self", "std", "super"}]
    )


def _lua_references(text: str) -> list[tuple[str, str]]:
    values = _matches(r"\brequire\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    return [("module", value) for value in values]


def _jvm_references(text: str) -> list[tuple[str, str]]:
    values = _matches(r"^\s*import\s+(?:static\s+)?([A-Za-z_][A-Za-z0-9_.$]*(?:\.[A-Za-z_*][A-Za-z0-9_*]*)?)", text)
    return [("symbol", value) for value in values]


def _dotnet_references(text: str) -> list[tuple[str, str]]:
    values = _matches(r"^\s*using\s+(?:static\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)\s*;", text)
    return [("symbol", value) for value in values]


def _elixir_references(text: str) -> list[tuple[str, str]]:
    values = _matches(r"^\s*(?:alias|import|require|use)\s+([A-Z][A-Za-z0-9_.]*)", text)
    return [("symbol", value) for value in values]


def _swift_references(text: str) -> list[tuple[str, str]]:
    values = _matches(r"^\s*import\s+(?:class|struct|enum|protocol|func|var|let|typealias\s+)?([A-Za-z_][A-Za-z0-9_.]*)", text)
    return [("symbol", value) for value in values]


SPECS = (
    LanguageSpec("rust", "rs", "rust_module", frozenset({".rs"}), _rust_references),
    LanguageSpec("ruby", "rb", "ruby_module", frozenset({".rb"}), _ruby_references),
    LanguageSpec("php", "php", "php_module", frozenset({".php"}), _php_references),
    LanguageSpec("native", "native", "native_module", frozenset({".c", ".cc", ".cpp", ".h", ".hpp"}), _native_references),
    LanguageSpec("jvm", "jvm", "jvm_module", frozenset({".java", ".kt", ".kts", ".scala"}), _jvm_references),
    LanguageSpec("dotnet", "dotnet", "dotnet_module", frozenset({".cs"}), _dotnet_references),
    LanguageSpec("lua", "lua", "lua_module", frozenset({".lua"}), _lua_references),
    LanguageSpec("elixir", "ex", "elixir_module", frozenset({".ex", ".exs"}), _elixir_references),
    LanguageSpec("swift", "swift", "swift_module", frozenset({".swift"}), _swift_references),
)

_LANGUAGE_RUNTIME_PREFIXES = {
    "rust": ("alloc", "core", "proc_macro", "std", "test"),
    "ruby": ("abbrev", "base64", "benchmark", "bigdecimal", "cgi", "csv", "date", "digest", "fileutils", "json", "logger", "net/", "openssl", "optparse", "pathname", "set", "stringio", "time", "uri", "yaml"),
    "jvm": ("java.", "javax.", "jdk.", "kotlin.", "scala."),
    "dotnet": ("Microsoft.CSharp", "System"),
    "elixir": ("Access", "Application", "Enum", "GenServer", "Kernel", "Logger", "Map", "Process", "Stream", "String", "Supervisor", "Task"),
    "swift": ("Combine", "CoreData", "CoreFoundation", "Darwin", "Dispatch", "Foundation", "Swift", "SwiftUI", "UIKit"),
}

_TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__"})


def _is_test(path_value: str, path: Path) -> bool:
    parts = {part.lower() for part in Path(path_value).parts}
    stem = path.stem
    stem_lower = stem.lower()
    return bool(parts & _TEST_DIRS) or any(
        (
            stem_lower.startswith("test_"),
            stem_lower.endswith("_test"),
            stem_lower.endswith("_spec"),
            stem.endswith("Test"),
            stem.endswith("Tests"),
            stem.endswith("Spec"),
            stem.endswith("Specs"),
        )
    )


def _node_id(spec: LanguageSpec, subject: Path, path: Path, tests: set[Path]) -> str:
    source = rel(subject, path)
    return f"test:{source}" if path in tests else f"{spec.prefix}:{source}"


def _is_language_runtime(spec: LanguageSpec, value: str) -> bool:
    return any(
        value == prefix or value.startswith(prefix)
        for prefix in _LANGUAGE_RUNTIME_PREFIXES.get(spec.name, ())
    )


def _code_text(spec: LanguageSpec, text: str) -> str:
    """Remove comments that can contain documentation examples of imports."""
    if spec.name in {"rust", "php", "native", "jvm", "dotnet", "swift"}:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"//.*$", "", text, flags=re.M)
    if spec.name == "ruby":
        text = re.sub(r"^=begin\b.*?^=end\b", "", text, flags=re.M | re.S)
        return re.sub(r"^\s*#.*$", "", text, flags=re.M)
    if spec.name == "lua":
        text = re.sub(r"--\[\[.*?\]\]", "", text, flags=re.S)
        return re.sub(r"--.*$", "", text, flags=re.M)
    if spec.name == "elixir":
        return re.sub(r"^\s*#.*$", "", text, flags=re.M)
    return text


def _declared_symbol(spec: LanguageSpec, text: str, path: Path) -> list[str]:
    if spec.name == "jvm":
        package = next(iter(_matches(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)", text)), "")
        return [f"{package}.{path.stem}".strip(".")]
    if spec.name == "dotnet":
        return _matches(r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)", text)
    if spec.name == "elixir":
        return _matches(r"^\s*defmodule\s+([A-Z][A-Za-z0-9_.]*)", text)
    return []


def _relative_candidates(source: Path, value: str, spec: LanguageSpec) -> list[Path]:
    raw = (source.parent / value.lstrip("/")).resolve()
    candidates = [raw]
    if not raw.suffix:
        candidates.extend(raw.with_suffix(suffix) for suffix in sorted(spec.suffixes))
        if spec.name == "ruby":
            candidates.append(raw / "init.rb")
        elif spec.name == "php":
            candidates.append(raw / "index.php")
    return candidates


def _resolve_reference(
    *,
    spec: LanguageSpec,
    source: Path,
    kind: str,
    value: str,
    files: set[Path],
    symbols: dict[str, set[Path]],
) -> Path | None:
    candidates: set[Path] = set()
    if kind == "relative":
        candidates.update(path for path in _relative_candidates(source, value, spec) if path in files)
    elif kind == "rust_mod":
        candidates.update(
            path
            for path in ((source.parent / f"{value}.rs").resolve(), (source.parent / value / "mod.rs").resolve())
            if path in files
        )
    elif kind == "rust_crate":
        first = value.split("::", 1)[0]
        candidates.update(path for path in files if path.name == f"{first}.rs" or path.as_posix().endswith(f"/{first}/mod.rs"))
    elif kind == "module" and spec.name == "lua":
        module_path = value.replace(".", "/")
        candidates.update(path for path in files if path.as_posix().endswith(f"/{module_path}.lua") or path.as_posix().endswith(f"/{module_path}/init.lua"))
    elif kind == "symbol":
        exact = value.removesuffix(".*")
        candidates.update(symbols.get(exact, set()))
        if not candidates and spec.name == "jvm" and "." in exact:
            candidates.update(symbols.get(exact.rsplit(".", 1)[0], set()))
    elif kind == "external":
        candidates.update(symbols.get(value, set()))
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _collect_spec(
    subject: Path,
    spec: LanguageSpec,
) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    files = {
        path.resolve()
        for path in subject.rglob("*")
        if path.is_file() and not skipped(subject, path) and path.suffix.lower() in spec.suffixes
    }
    tests = {path for path in files if _is_test(rel(subject, path), path)}
    nodes = [
        StaticNode(
            id=_node_id(spec, subject, path, tests),
            type="test_module" if path in tests else spec.node_type,
            source=rel(subject, path),
        )
        for path in sorted(files)
    ]
    texts: dict[Path, str] = {}
    symbols: dict[str, set[Path]] = {}
    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        code = _code_text(spec, text)
        texts[path] = code
        for symbol in _declared_symbol(spec, code, path):
            symbols.setdefault(symbol, set()).add(path)
    if spec.name == "rust":
        for manifest in subject.rglob("Cargo.toml"):
            if skipped(subject, manifest):
                continue
            try:
                manifest_text = manifest.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            package = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', manifest_text, re.M)
            if package is None:
                continue
            candidates = {
                candidate.resolve()
                for candidate in (manifest.parent / "src" / "lib.rs", manifest.parent / "src" / "main.rs")
                if candidate.resolve() in files
            }
            if len(candidates) == 1:
                symbols.setdefault(package.group(1).replace("-", "_"), set()).update(candidates)

    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    for path, text in texts.items():
        source_value = rel(subject, path)
        source_id = _node_id(spec, subject, path, tests)
        for kind, value in spec.references(text):
            target = _resolve_reference(
                spec=spec,
                source=path,
                kind=kind,
                value=value,
                files=files,
                symbols=symbols,
            )
            if target is not None and target != path:
                target_id = _node_id(spec, subject, target, tests)
                edge_type = "tests" if path in tests and target not in tests else "imports"
                edges.add(StaticEdge(source_id, target_id, edge_type, source_value))
            elif kind in {"external", "symbol"} and not _is_language_runtime(spec, value):
                unresolved.append({"specifier": value, "from": source_value})
            elif kind in {"relative", "rust_mod", "module"}:
                unresolved.append({"specifier": value, "from": source_value})
    return nodes, sorted(edges, key=lambda item: (item.source, item.target, item.type)), unresolved


_GO_IMPORT_RE = re.compile(r'^\s*import\s+(?:[A-Za-z_.][A-Za-z0-9_.]*\s+)?"([^"]+)"', re.M)
_GO_IMPORT_BLOCK_RE = re.compile(r"\bimport\s*\((.*?)\)", re.S)
_GO_BLOCK_VALUE_RE = re.compile(r'(?:^|\s)(?:[A-Za-z_.][A-Za-z0-9_.]*\s+)?"([^"]+)"')


def _go_modules(subject: Path) -> dict[Path, str]:
    modules: dict[Path, str] = {}
    for path in subject.rglob("go.mod"):
        if skipped(subject, path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        match = re.search(r"^\s*module\s+(\S+)", text, re.M)
        if match:
            modules[path.parent.resolve()] = match.group(1)
    return modules


def _nearest_go_module(directory: Path, modules: dict[Path, str]) -> tuple[Path, str] | None:
    candidates = [(root, name) for root, name in modules.items() if directory == root or root in directory.parents]
    return max(candidates, key=lambda item: len(item[0].parts)) if candidates else None


def _go_imports(text: str) -> list[str]:
    values = _GO_IMPORT_RE.findall(text)
    for block in _GO_IMPORT_BLOCK_RE.findall(text):
        values.extend(_GO_BLOCK_VALUE_RE.findall(block))
    return values


def collect_go_graph(subject: Path) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    files = {
        path.resolve()
        for path in subject.rglob("*.go")
        if path.is_file() and not skipped(subject, path)
    }
    tests = {path for path in files if _is_test(rel(subject, path), path)}
    production = files - tests
    modules = _go_modules(subject)
    package_by_dir: dict[Path, str] = {}
    nodes: list[StaticNode] = []
    for directory in sorted({path.parent for path in production}):
        owner = _nearest_go_module(directory, modules)
        if owner:
            module_root, module_name = owner
            within_module = directory.relative_to(module_root).as_posix()
            package_name = module_name if within_module == "." else f"{module_name}/{within_module}"
        else:
            package_name = directory.relative_to(subject).as_posix()
        package_id = f"go:package:{package_name or '.'}"
        package_by_dir[directory] = package_id
        representative = sorted(path for path in production if path.parent == directory)[0]
        nodes.append(StaticNode(package_id, "go_package", rel(subject, representative)))
    for path in sorted(files):
        nodes.append(
            StaticNode(
                f"test:{rel(subject, path)}" if path in tests else f"go:{rel(subject, path)}",
                "test_module" if path in tests else "go_module",
                rel(subject, path),
            )
        )
    edges: set[StaticEdge] = set()
    unresolved: list[dict[str, str]] = []
    package_by_import = {package_id.removeprefix("go:package:"): package_id for package_id in package_by_dir.values()}
    for path in sorted(files):
        source_value = rel(subject, path)
        source_id = f"test:{source_value}" if path in tests else f"go:{source_value}"
        own_package = package_by_dir.get(path.parent)
        if own_package:
            edges.add(StaticEdge(source_id, own_package, "tests" if path in tests else "member_of", source_value))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for value in _go_imports(text):
            target = package_by_import.get(value)
            if target and target != own_package:
                edges.add(StaticEdge(source_id, target, "tests" if path in tests else "imports", source_value))
            elif not target and (
                any(value == name or value.startswith(name + "/") for name in modules.values())
                or "." in value.split("/", 1)[0]
            ):
                unresolved.append({"specifier": value, "from": source_value})
    return nodes, sorted(edges, key=lambda item: (item.source, item.target, item.type)), unresolved


def collect_additional_language_graph(
    subject: Path,
) -> tuple[list[StaticNode], list[StaticEdge], list[dict[str, str]]]:
    nodes: list[StaticNode] = []
    edges: list[StaticEdge] = []
    unresolved: list[dict[str, str]] = []
    go_nodes, go_edges, go_unresolved = collect_go_graph(subject)
    nodes.extend(go_nodes)
    edges.extend(go_edges)
    unresolved.extend(go_unresolved)
    for spec in SPECS:
        spec_nodes, spec_edges, spec_unresolved = _collect_spec(subject, spec)
        nodes.extend(spec_nodes)
        edges.extend(spec_edges)
        unresolved.extend(spec_unresolved)
    return nodes, edges, unresolved
