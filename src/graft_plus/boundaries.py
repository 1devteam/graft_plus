"""Source-backed ledger for relationships static reconstruction cannot prove.

These facts identify the exact place where a model or reviewer needs build or
runtime context.  They never synthesize an edge or claim a dynamic target.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from graft_plus.inventory import rel, relevant_files

MAX_EVIDENCE = 240


def _evidence(value: str) -> str:
    return " ".join(value.strip().split())[:MAX_EVIDENCE]


def _row(
    *,
    kind: str,
    status: str,
    source: str,
    line: int,
    language: str,
    evidence: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "source": source,
        "line": line,
        "language": language,
        "evidence": _evidence(evidence),
        "reason": reason,
    }


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _python_boundaries(source: str, text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text, filename=source)
    except SyntaxError:
        return []
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        line = int(getattr(node, "lineno", 1))
        segment = ast.get_source_segment(text, node) or ""
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            rows.append(
                _row(
                    kind="wildcard_import",
                    status="unresolved",
                    source=source,
                    line=line,
                    language="python",
                    evidence=segment,
                    reason="Wildcard membership depends on the imported module at this revision.",
                )
            )
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func) or ""
        if name in {"__import__", "importlib.import_module", "importlib.util.spec_from_file_location"}:
            argument = node.args[0] if node.args else None
            rows.append(
                _row(
                    kind="dynamic_load",
                    status="unresolved" if _literal(argument) is None else "declared",
                    source=source,
                    line=line,
                    language="python",
                    evidence=segment,
                    reason="The dynamic import API requires runtime evaluation; a literal argument is recorded but not promoted to an edge.",
                )
            )
        short_name = name.rsplit(".", 1)[-1]
        container_call = name.startswith(("container.", "injector.")) and short_name in {
            "get",
            "provide",
            "resolve",
        }
        if short_name in {"Depends", "Inject", "Provide"} or container_call:
            rows.append(
                _row(
                    kind="dependency_injection",
                    status="unresolved",
                    source=source,
                    line=line,
                    language="python",
                    evidence=segment,
                    reason="Container or framework resolution selects the runtime provider.",
                )
            )
        if name.rsplit(".", 1)[-1] in {"include_router", "include", "mount"}:
            rows.append(
                _row(
                    kind="route_composition",
                    status="declared",
                    source=source,
                    line=line,
                    language="python",
                    evidence=segment,
                    reason="Source declares route composition; the graph does not synthesize a runtime-prefixed route.",
                )
            )
    return rows


LINE_PATTERNS: tuple[tuple[str, str, str, re.Pattern[str], str], ...] = (
    (
        "dynamic_load",
        "unresolved",
        "javascript",
        re.compile(r"\b(?:import|require)\s*\(\s*(?!['\"])[^)]+\)"),
        "The module expression is computed at runtime.",
    ),
    (
        "dependency_injection",
        "unresolved",
        "javascript",
        re.compile(r"\b(?:container|injector)\.(?:get|resolve|register)|@(?:Inject|Injectable)\b"),
        "Container registration or lookup selects the runtime provider.",
    ),
    (
        "route_composition",
        "declared",
        "javascript",
        re.compile(r"\b(?:app|router|server)\.(?:use|register)\s*\("),
        "Source declares router composition; runtime prefixes are not synthesized.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "ruby",
        re.compile(r"^\s*(?:require|require_relative|load)\s+(?!['\"])[^#]+"),
        "The required path is computed at runtime.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "php",
        re.compile(r"\b(?:include|include_once|require|require_once)\s*(?!\(?\s*(?:__DIR__\s*\.\s*)?['\"])[^;]+"),
        "The included path is computed at runtime.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "jvm",
        re.compile(r"\b(?:Class\.forName|ServiceLoader\.load)\s*\("),
        "Reflection or service loading selects the runtime implementation.",
    ),
    (
        "wildcard_import",
        "unresolved",
        "jvm",
        re.compile(r"^\s*import\s+(?:static\s+)?[A-Za-z_][A-Za-z0-9_.]*\.\*\s*;?"),
        "Wildcard membership depends on the imported package at this revision.",
    ),
    (
        "dependency_injection",
        "unresolved",
        "jvm",
        re.compile(r"@(?:Inject|Autowired)\b"),
        "Framework injection selects the runtime provider.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "dotnet",
        re.compile(r"\b(?:Assembly\.Load|Activator\.CreateInstance)\s*\("),
        "Reflection selects the runtime assembly or implementation.",
    ),
    (
        "dependency_injection",
        "unresolved",
        "dotnet",
        re.compile(r"\.(?:AddScoped|AddSingleton|AddTransient)\s*(?:<|\()|\[Inject\]"),
        "The service container selects the runtime implementation.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "go",
        re.compile(r"\bplugin\.Open\s*\("),
        "A plugin path is resolved at runtime.",
    ),
    (
        "dependency_injection",
        "unresolved",
        "go",
        re.compile(r"\b(?:wire\.Build|fx\.Provide|dig\.New)\s*\("),
        "Generated or runtime container wiring selects providers.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "rust",
        re.compile(r"\b(?:Library|libloading::Library)::?new\s*\("),
        "A shared library path is resolved at runtime.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "lua",
        re.compile(r"\brequire\s*\(\s*(?!['\"])[^)]+\)"),
        "The required module is computed at runtime.",
    ),
    (
        "dynamic_load",
        "unresolved",
        "elixir",
        re.compile(r"\b(?:Module\.concat|Code\.require_file|apply)\s*\("),
        "The module or callable is assembled at runtime.",
    ),
)


SUFFIX_LANGUAGE = {
    ".bash": "shell",
    ".c": "native",
    ".cc": "native",
    ".cjs": "javascript",
    ".cpp": "native",
    ".cs": "dotnet",
    ".cts": "javascript",
    ".ex": "elixir",
    ".exs": "elixir",
    ".go": "go",
    ".h": "native",
    ".hpp": "native",
    ".java": "jvm",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "jvm",
    ".kts": "jvm",
    ".lua": "lua",
    ".mjs": "javascript",
    ".mts": "javascript",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "jvm",
    ".sh": "shell",
    ".swift": "swift",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".zsh": "shell",
}

GENERATED_MARKERS = re.compile(r"(?:do not edit|<auto-generated|@generated|this file (?:is|was) generated)", re.I)
CODEGEN_RE = re.compile(r"\b(?:codegen|generate|generated|protoc|openapi-generator|graphql-codegen|go:generate)\b", re.I)
BUILD_MAPPING_RE = re.compile(
    r'"(?:paths|exports|imports|autoload)"\s*:|<ProjectReference\b|^\s*replace\s+\S+\s+=>|\bsourceSets\b|\bPackage\s*\(',
    re.I,
)

BUILD_FILES = frozenset(
    {
        "Cargo.toml",
        "Gemfile",
        "Makefile",
        "Package.swift",
        "Rakefile",
        "build.gradle",
        "build.gradle.kts",
        "composer.json",
        "go.mod",
        "mix.exs",
        "package.json",
        "pom.xml",
        "pyproject.toml",
        "settings.gradle",
        "settings.gradle.kts",
        "tsconfig.json",
    }
)


def _is_build_file(path: Path) -> bool:
    return path.name in BUILD_FILES or path.suffix.lower() in {".csproj", ".fsproj", ".gradle", ".vbproj"}


def _line_boundaries(path: Path, source: str, text: str) -> list[dict[str, Any]]:
    language = SUFFIX_LANGUAGE.get(path.suffix.lower(), "build")
    rows: list[dict[str, Any]] = []
    in_block_comment = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        generated_header = number <= 5 and stripped.startswith(("#", "//", "/*", "*", "<!--"))
        generated_marker = generated_header and bool(GENERATED_MARKERS.search(line))
        if generated_marker:
            rows.append(
                _row(
                    kind="generated_source",
                    status="declared",
                    source=source,
                    line=number,
                    language=language,
                    evidence=line,
                    reason="The file declares that a generator, not a human, owns this source.",
                )
            )
        codegen_declaration = _is_build_file(path) or bool(
            path.suffix.lower() == ".go" and re.match(r"^\s*//go:generate\b", line)
        )
        if not generated_marker and codegen_declaration and CODEGEN_RE.search(line):
            rows.append(
                _row(
                    kind="code_generation",
                    status="declared",
                    source=source,
                    line=number,
                    language=language,
                    evidence=line,
                    reason="Source or build configuration declares a generation step.",
                )
            )
        if _is_build_file(path) and BUILD_MAPPING_RE.search(line):
            rows.append(
                _row(
                    kind="build_module_mapping",
                    status="declared",
                    source=source,
                    line=number,
                    language=language,
                    evidence=line,
                    reason="Build configuration can alter source-module resolution.",
                )
            )
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if stripped.startswith(("#", "//", "--", "*")):
            continue
        if stripped.startswith(("'", '"', "`")):
            continue
        for kind, status, pattern_language, pattern, reason in LINE_PATTERNS:
            if pattern_language != language or not pattern.search(line):
                continue
            rows.append(
                _row(
                    kind=kind,
                    status=status,
                    source=source,
                    line=number,
                    language=language,
                    evidence=line,
                    reason=reason,
                )
            )
    return rows


def collect_relationship_boundaries(subject: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in relevant_files(subject):
        source = rel(subject, path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if path.suffix.lower() == ".py":
            rows.extend(_python_boundaries(source, text))
        rows.extend(_line_boundaries(path, source, text))
    unique = {
        (row["kind"], row["status"], row["source"], row["line"], row["evidence"]): row
        for row in rows
    }
    ordered = sorted(
        unique.values(),
        key=lambda row: (str(row["source"]), int(row["line"]), str(row["kind"]), str(row["evidence"])),
    )
    counts = Counter(str(row["kind"]) for row in ordered)
    unresolved = sum(1 for row in ordered if row["status"] == "unresolved")
    return {
        "relationship_boundaries": ordered,
        "relationship_boundary_count": len(ordered),
        "unresolved_relationship_boundary_count": unresolved,
        "relationship_boundary_counts_by_kind": dict(sorted(counts.items())),
    }
