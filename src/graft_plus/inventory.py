"""Universal file, package-manifest, and intent inventory.

The canonical graph stays source-backed.  Files that do not have a language
adapter are still represented so absence of an extractor cannot masquerade as
absence from the repository.
"""

from __future__ import annotations

import json
import re
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}

SOURCE_SUFFIXES = {
    ".bash",
    ".c",
    ".cc",
    ".cjs",
    ".cpp",
    ".cs",
    ".cts",
    ".ex",
    ".exs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".mjs",
    ".mts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
TEST_SUFFIXES = {".bats"}
DOCUMENT_SUFFIXES = {".adoc", ".md", ".rst"}
CONFIG_SUFFIXES = {".cfg", ".ini", ".json", ".toml", ".yaml", ".yml"}
CONTRACT_SUFFIXES = {".avsc", ".gql", ".graphql", ".proto", ".sql"}
BUILD_SUFFIXES = {".bazel", ".bzl", ".cmake", ".csproj", ".fsproj", ".gn", ".gni", ".gradle", ".ninja", ".vbproj"}
BUILD_FILES = {
    ".gn",
    "BUILD",
    "BUILD.bazel",
    "BUILD.gn",
    "CMakeLists.txt",
    "Cargo.lock",
    "Cargo.toml",
    "DEPS",
    "GNUmakefile",
    "Gemfile",
    "Makefile",
    "MODULE.bazel",
    "Package.swift",
    "Rakefile",
    "SConscript",
    "SConstruct",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "go.mod",
    "go.sum",
    "meson.build",
    "meson_options.txt",
    "mix.exs",
    "package-lock.json",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
    "settings.gradle.kts",
}
GOVERNANCE_FILES = {"CODEOWNERS", "OWNERS", "PRESUBMIT.py", "SECURITY.md"}
SPECIAL_FILES = {
    *BUILD_FILES,
    *GOVERNANCE_FILES,
    ".env.example",
    "Dockerfile",
    "Makefile",
    "Procfile",
    "go.mod",
    "go.sum",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.lock",
    "Cargo.toml",
    "Gemfile",
    "Package.swift",
    "Rakefile",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "mix.exs",
    "pom.xml",
    "settings.gradle",
    "settings.gradle.kts",
}
INTENT_NAME_RE = re.compile(
    r"(?:^|[-_.])(readme|architecture|adr|design|specification|spec|plan|status|roadmap|contributing)(?:$|[-_.])",
    re.I,
)
TEST_PATH_RE = re.compile(r"(?:^|/)(?:tests?|specs?|__tests__)(?:/|$)|(?:\.test|\.spec)\.[^.]+$", re.I)
CONFIG_NAME_RE = re.compile(
    r"(?:^|[-_.])(config|settings|schema|manifest|lock|workspace)(?:$|[-_.])|^(?:tsconfig|jsconfig|docker-compose)",
    re.I,
)


def rel(subject: Path, path: Path) -> str:
    return str(path.relative_to(subject)).replace("\\", "/")


def skipped(subject: Path, path: Path) -> bool:
    try:
        parts = path.relative_to(subject).parts
    except ValueError:
        return True
    return any(part in SKIP_DIRS for part in parts)


def relevant_files(subject: Path) -> list[Path]:
    """Return deterministic repository files that carry system or intent facts."""
    found: list[Path] = []
    for path in subject.rglob("*"):
        if not path.is_file() or path.is_symlink() or skipped(subject, path):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        suffix = path.suffix.lower()
        path_value = rel(subject, path)
        parts = {part.lower() for part in Path(path_value).parts}
        fixture_manifest = path.name in {"package.json", "pyproject.toml"} and bool(
            parts & {"fixture", "fixtures", "test", "tests", "__tests__"}
        )
        config_bearing = suffix in CONFIG_SUFFIXES and (
            len(Path(path_value).parts) == 1
            or path_value.startswith(".github/")
            or bool(CONFIG_NAME_RE.search(path.name))
        )
        if fixture_manifest:
            continue
        if suffix in SOURCE_SUFFIXES | TEST_SUFFIXES | DOCUMENT_SUFFIXES | CONTRACT_SUFFIXES | BUILD_SUFFIXES or config_bearing or path.name in SPECIAL_FILES:
            found.append(path)
            continue
        try:
            with path.open("rb") as handle:
                first = handle.readline(256)
        except OSError:
            continue
        if first.startswith(b"#!") and any(shell in first for shell in (b"sh", b"bash", b"zsh", b"python", b"node")):
            found.append(path)
    return sorted(found, key=lambda item: rel(subject, item))


def language(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".bats": "shell",
        ".bash": "shell",
        ".c": "c",
        ".cc": "cpp",
        ".cjs": "javascript",
        ".cpp": "cpp",
        ".cs": "csharp",
        ".cts": "typescript",
        ".ex": "elixir",
        ".exs": "elixir",
        ".go": "go",
        ".h": "c",
        ".hpp": "cpp",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".lua": "lua",
        ".md": "markdown",
        ".mjs": "javascript",
        ".mts": "typescript",
        ".php": "php",
        ".py": "python",
        ".rb": "ruby",
        ".rs": "rust",
        ".scala": "scala",
        ".sh": "shell",
        ".swift": "swift",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".zsh": "shell",
        ".avsc": "avro",
        ".gql": "graphql",
        ".graphql": "graphql",
        ".proto": "protobuf",
        ".sql": "sql",
        ".csproj": "msbuild",
        ".fsproj": "msbuild",
        ".gradle": "gradle",
        ".vbproj": "msbuild",
    }.get(suffix, "other")


def is_test(path_value: str, path: Path) -> bool:
    return path.suffix.lower() == ".bats" or bool(TEST_PATH_RE.search(path_value))


def intent_kind(path_value: str, path: Path) -> str | None:
    name = path.name.lower()
    if name in {"package.json", "pyproject.toml", "cargo.toml", "go.mod"}:
        return "manifest"
    if name.startswith("readme"):
        return "readme"
    if path.suffix.lower() not in DOCUMENT_SUFFIXES:
        return None
    if "adr" in {part.lower() for part in path.parts} or re.search(r"(?:^|[-_.])adr(?:$|[-_.])", name):
        return "architecture-decision"
    if INTENT_NAME_RE.search(name) or any(
        token in path_value.lower() for token in ("/architecture/", "/design/", "/specs/", "/planning/")
    ):
        return "declared-intent"
    return None


def classify(path_value: str, path: Path) -> str:
    if path.name in GOVERNANCE_FILES:
        return "governance_file"
    if path.name in BUILD_FILES or path.suffix.lower() in BUILD_SUFFIXES:
        return "build_file"
    if is_test(path_value, path):
        return "test_file"
    if path.suffix.lower() in SOURCE_SUFFIXES or path.suffix.lower() in TEST_SUFFIXES:
        return "source_file"
    if path.suffix.lower() in DOCUMENT_SUFFIXES:
        return "documentation"
    if path.suffix.lower() in CONTRACT_SUFFIXES:
        return "contract_source"
    return "configuration"


def inventory_nodes(
    subject: Path,
    *,
    mapped_sources: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add fallback file nodes and report relationship-parser coverage."""
    nodes: list[dict[str, Any]] = []
    all_files = relevant_files(subject)
    relationship_candidates: list[str] = []
    inventory_only: list[str] = []
    intent_sources: list[dict[str, str]] = []
    for path in all_files:
        path_value = rel(subject, path)
        kind = intent_kind(path_value, path)
        if kind:
            intent_sources.append({"path": path_value, "kind": kind})
        if path.suffix.lower() in SOURCE_SUFFIXES | TEST_SUFFIXES:
            relationship_candidates.append(path_value)
        if path_value in mapped_sources:
            continue
        inventory_only.append(path_value)
        nodes.append(
            {
                "id": f"file:{path_value}",
                "type": classify(path_value, path),
                "source": path_value,
                "layer": "generated",
                "language": language(path),
                "relationship_status": "inventory_only",
                "intent_kind": kind,
            }
        )
    parsed = sorted(set(relationship_candidates) & mapped_sources)
    unparsed = sorted(set(relationship_candidates) - mapped_sources)
    return nodes, {
        "file_count": len(all_files),
        "relationship_candidate_count": len(set(relationship_candidates)),
        "relationship_parsed_file_count": len(parsed),
        "relationship_unparsed_file_count": len(unparsed),
        "relationship_unparsed_files": unparsed,
        "inventory_only_files": sorted(inventory_only),
        "intent_sources": sorted(intent_sources, key=lambda item: (item["kind"], item["path"])),
    }


def _package_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _pyproject(path: Path) -> dict[str, Any] | None:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    project = payload.get("project")
    return project if isinstance(project, dict) else None


def _target_id(source: str, source_node_ids: dict[str, str]) -> str | None:
    normalized = source.removeprefix("./")
    return source_node_ids.get(normalized)


def collect_package_topology(
    subject: Path,
    source_node_ids: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read portable declared package topology without judging its correctness."""
    packages: dict[str, dict[str, Any]] = {}
    package_paths: dict[str, str] = {}
    declarations: list[tuple[str, dict[str, Any], str]] = []
    for path in relevant_files(subject):
        path_value = rel(subject, path)
        payload: dict[str, Any] | None = None
        kind = ""
        if path.name == "package.json":
            if set(Path(path_value).parts) & {"fixture", "fixtures", "test", "tests", "__tests__"}:
                continue
            payload = _package_json(path)
            kind = "npm"
        elif path.name == "pyproject.toml":
            if set(Path(path_value).parts) & {"fixture", "fixtures", "test", "tests", "__tests__"}:
                continue
            payload = _pyproject(path)
            kind = "python"
        if not payload:
            continue
        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raw_name = "." if path.parent == subject else rel(subject, path.parent)
        name = raw_name.strip()
        package_id = f"package:{name}"
        if package_id in packages:
            package_id = f"package:{name}:{path_value}"
        description = payload.get("description")
        node = {
            "id": package_id,
            "type": "software_package",
            "source": path_value,
            "layer": "generated",
            "name": name,
            "ecosystem": kind,
            "description": description if isinstance(description, str) else None,
        }
        if kind == "npm":
            scripts = payload.get("scripts")
            node["scripts"] = scripts if isinstance(scripts, dict) else {}
        packages[package_id] = node
        package_paths[path_value] = package_id
        declarations.append((package_id, payload, path_value))

    edges: list[dict[str, Any]] = []
    dependency_nodes: dict[str, dict[str, Any]] = {}
    package_by_name = {str(node["name"]): package_id for package_id, node in packages.items()}
    for package_id, payload, path_value in declarations:
        manifest_id = f"manifest:{path_value}"
        if manifest_id in set(source_node_ids.values()):
            edges.append(
                {"from": package_id, "to": manifest_id, "type": "declared_in", "evidence": path_value, "layer": "generated"}
            )
        parent = Path(path_value).parent
        entrypoints: list[tuple[str, str]] = []
        if path_value.endswith("package.json"):
            main = payload.get("main")
            if isinstance(main, str):
                entrypoints.append(("main", main))
            bin_value = payload.get("bin")
            if isinstance(bin_value, str):
                entrypoints.append(("bin", bin_value))
            elif isinstance(bin_value, dict):
                entrypoints.extend((f"bin:{name}", value) for name, value in bin_value.items() if isinstance(value, str))
        else:
            scripts = payload.get("scripts")
            if isinstance(scripts, dict):
                entrypoints.extend((f"script:{name}", value) for name, value in scripts.items() if isinstance(value, str))
        for role, raw_target in entrypoints:
            target_path = str((parent / raw_target).as_posix()).removeprefix("./")
            target = _target_id(target_path, source_node_ids)
            if target:
                edges.append(
                    {
                        "from": package_id,
                        "to": target,
                        "type": "declares_entrypoint",
                        "role": role,
                        "evidence": path_value,
                        "layer": "generated",
                    }
                )
        dependency_maps = []
        for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            value = payload.get(key)
            if isinstance(value, dict):
                dependency_maps.append((key, value))
        raw_dependencies = payload.get("dependencies")
        if isinstance(raw_dependencies, list):
            dependency_maps.append(("dependencies", {str(value): "declared" for value in raw_dependencies}))
        for scope, mapping in dependency_maps:
            for dependency, constraint in sorted(mapping.items()):
                if not isinstance(dependency, str):
                    continue
                target = package_by_name.get(dependency)
                if target is None:
                    target = f"dependency:{dependency}"
                    dependency_nodes.setdefault(
                        target,
                        {
                            "id": target,
                            "type": "external_dependency",
                            "source": path_value,
                            "layer": "generated",
                            "name": dependency,
                        },
                    )
                edges.append(
                    {
                        "from": package_id,
                        "to": target,
                        "type": "depends_on_package",
                        "scope": scope,
                        "constraint": str(constraint),
                        "evidence": path_value,
                        "layer": "generated",
                    }
                )

    package_items = list(packages.values())
    for root_id, payload, root_path in declarations:
        workspaces = payload.get("workspaces")
        patterns: list[str] = []
        if isinstance(workspaces, list):
            patterns = [str(item) for item in workspaces]
        elif isinstance(workspaces, dict) and isinstance(workspaces.get("packages"), list):
            patterns = [str(item) for item in workspaces["packages"]]
        root_parent = Path(root_path).parent
        for child_path, child_id in package_paths.items():
            if child_id == root_id:
                continue
            child_parent = Path(child_path).parent
            try:
                relative = child_parent.relative_to(root_parent).as_posix()
            except ValueError:
                continue
            if any(fnmatch(relative, pattern.rstrip("/")) for pattern in patterns):
                edges.append(
                    {
                        "from": root_id,
                        "to": child_id,
                        "type": "contains_workspace",
                        "evidence": root_path,
                        "layer": "generated",
                    }
                )
    return sorted([*package_items, *dependency_nodes.values()], key=lambda item: str(item["id"])), sorted(
        edges, key=lambda item: (str(item["from"]), str(item["to"]), str(item["type"]), str(item.get("role") or ""))
    )
