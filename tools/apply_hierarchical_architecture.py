from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


# inventory.py: admit architecture-control surfaces and classify them semantically.
p = Path("src/graft_plus/inventory.py")
text = p.read_text()
text = text.replace(
    'BUILD_SUFFIXES = {".csproj", ".fsproj", ".gradle", ".vbproj"}\nSPECIAL_FILES = {\n',
    '''BUILD_SUFFIXES = {".bazel", ".bzl", ".cmake", ".csproj", ".fsproj", ".gn", ".gni", ".gradle", ".ninja", ".vbproj"}\nBUILD_FILES = {\n    ".gn",\n    "BUILD",\n    "BUILD.bazel",\n    "BUILD.gn",\n    "CMakeLists.txt",\n    "DEPS",\n    "GNUmakefile",\n    "Makefile",\n    "MODULE.bazel",\n    "SConscript",\n    "SConstruct",\n    "WORKSPACE",\n    "WORKSPACE.bazel",\n    "meson.build",\n    "meson_options.txt",\n}\nGOVERNANCE_FILES = {"CODEOWNERS", "OWNERS", "PRESUBMIT.py", "SECURITY.md"}\nSPECIAL_FILES = {\n    *BUILD_FILES,\n    *GOVERNANCE_FILES,\n''',
    1,
)
old = '''def classify(path_value: str, path: Path) -> str:\n    if is_test(path_value, path):\n        return "test_file"\n    if path.suffix.lower() in SOURCE_SUFFIXES or path.suffix.lower() in TEST_SUFFIXES:\n        return "source_file"\n'''
new = '''def classify(path_value: str, path: Path) -> str:\n    if path.name in GOVERNANCE_FILES:\n        return "governance_file"\n    if path.name in BUILD_FILES or path.suffix.lower() in BUILD_SUFFIXES:\n        return "build_file"\n    if is_test(path_value, path):\n        return "test_file"\n    if path.suffix.lower() in SOURCE_SUFFIXES or path.suffix.lower() in TEST_SUFFIXES:\n        return "source_file"\n'''
if old not in text:
    raise SystemExit("inventory classify marker missing")
text = text.replace(old, new, 1)
p.write_text(text)

# architecture.py: empty repositories must remain valid subjects.
p = Path("src/graft_plus/architecture.py")
text = p.read_text()
marker = '''    source_paths = sorted({str(node["source"]) for node in file_level_nodes})\n    subsystem_paths: set[str] = {"."}\n'''
replacement = '''    source_paths = sorted({str(node["source"]) for node in file_level_nodes})\n    if not source_paths and not controls:\n        return [], [], {\n            "subsystem_count": 0,\n            "subsystem_direct_member_counts": {},\n            "cross_language_subsystem_count": 0,\n            "cross_language_subsystems": [],\n            "build_definition_count": 0,\n            "build_definition_counts_by_system": {},\n            "build_input_edge_count": 0,\n            "governance_boundary_count": 0,\n            "governance_boundary_counts_by_kind": {},\n            "source_provenance_counts": {},\n        }, {}\n    subsystem_paths: set[str] = {"."}\n'''
if marker not in text:
    raise SystemExit("architecture empty-subject marker missing")
p.write_text(text.replace(marker, replacement, 1))

# graph.py: integrate the shared architecture layer after all portable source-backed collectors.
p = Path("src/graft_plus/graph.py")
text = p.read_text()
text = text.replace(
    'from graft_plus.adapters import collect_javascript_graph, collect_shell_graph\n',
    'from graft_plus.adapters import collect_javascript_graph, collect_shell_graph\nfrom graft_plus.architecture import collect_architecture_topology\n',
    1,
)
old = '''    configuration_nodes, configuration_edges, configuration_facts = collect_configuration_graph(\n        subject, source_node_ids\n    )\n    nodes.extend(configuration_nodes)\n    edges.extend(configuration_edges)\n    mapped_sources = {\n'''
new = '''    configuration_nodes, configuration_edges, configuration_facts = collect_configuration_graph(\n        subject, source_node_ids\n    )\n    nodes.extend(configuration_nodes)\n    edges.extend(configuration_edges)\n    architecture_nodes, architecture_edges, architecture_facts, architecture_annotations = collect_architecture_topology(\n        subject, nodes\n    )\n    for node in nodes:\n        annotation = architecture_annotations.get(str(node.get("id") or ""))\n        if annotation:\n            node.update(annotation)\n    nodes.extend(architecture_nodes)\n    edges.extend(architecture_edges)\n    mapped_sources = {\n'''
if old not in text:
    raise SystemExit("graph architecture integration marker missing")
text = text.replace(old, new, 1)
text = text.replace('        "schema_version": "1.6",\n', '        "schema_version": "1.7",\n', 1)
text = text.replace(
    '                "configuration-deployment",\n                "evidence-anchors",\n',
    '                "configuration-deployment",\n                "subsystem-hierarchy",\n                "build-system-topology",\n                "source-provenance",\n                "cross-language-subsystem-joins",\n                "governance-boundaries",\n                "evidence-anchors",\n',
    1,
)
text = text.replace(
    '            **configuration_facts,\n            "evidence_precision_counts": evidence_precision_counts,\n',
    '            **configuration_facts,\n            **architecture_facts,\n            "evidence_precision_counts": evidence_precision_counts,\n',
    1,
)
text = text.replace(
    '            "deployment_fact_count": configuration_facts["deployment_fact_count"],\n            "evidence_precision_counts": evidence_precision_counts,\n',
    '            "deployment_fact_count": configuration_facts["deployment_fact_count"],\n            "subsystem_count": architecture_facts["subsystem_count"],\n            "cross_language_subsystem_count": architecture_facts["cross_language_subsystem_count"],\n            "build_definition_count": architecture_facts["build_definition_count"],\n            "build_input_edge_count": architecture_facts["build_input_edge_count"],\n            "governance_boundary_count": architecture_facts["governance_boundary_count"],\n            "source_provenance_counts": architecture_facts["source_provenance_counts"],\n            "evidence_precision_counts": evidence_precision_counts,\n',
    1,
)
p.write_text(text)

# completeness.py: architecture is an explicit boundary and its coverage facts survive assurance.
p = Path("src/graft_plus/completeness.py")
text = p.read_text()
text = text.replace(
    '    "runtime": "runtime",\n',
    '    "runtime": "runtime",\n    "subsystem": "subsystem",\n    "build_definition": "build-system",\n    "governance_boundary": "governance",\n',
    1,
)
text = text.replace('        "schema_version": "1.2",\n', '        "schema_version": "1.3",\n', 1)
old = '''        "deployment_fact_counts_by_kind": dict(\n            (graph.get("facts") or {}).get("deployment_fact_counts_by_kind") or {}\n        ),\n        "stale_graph_source_count": coverage.get("stale_graph_source_count", 0),\n'''
new = '''        "deployment_fact_counts_by_kind": dict(\n            (graph.get("facts") or {}).get("deployment_fact_counts_by_kind") or {}\n        ),\n        "subsystem_count": int((graph.get("facts") or {}).get("subsystem_count") or 0),\n        "subsystem_direct_member_counts": dict((graph.get("facts") or {}).get("subsystem_direct_member_counts") or {}),\n        "cross_language_subsystem_count": int((graph.get("facts") or {}).get("cross_language_subsystem_count") or 0),\n        "cross_language_subsystems": list((graph.get("facts") or {}).get("cross_language_subsystems") or []),\n        "build_definition_count": int((graph.get("facts") or {}).get("build_definition_count") or 0),\n        "build_definition_counts_by_system": dict((graph.get("facts") or {}).get("build_definition_counts_by_system") or {}),\n        "build_input_edge_count": int((graph.get("facts") or {}).get("build_input_edge_count") or 0),\n        "governance_boundary_count": int((graph.get("facts") or {}).get("governance_boundary_count") or 0),\n        "governance_boundary_counts_by_kind": dict((graph.get("facts") or {}).get("governance_boundary_counts_by_kind") or {}),\n        "source_provenance_counts": dict((graph.get("facts") or {}).get("source_provenance_counts") or {}),\n        "stale_graph_source_count": coverage.get("stale_graph_source_count", 0),\n'''
if old not in text:
    raise SystemExit("completeness architecture facts marker missing")
p.write_text(text.replace(old, new, 1))

# decision.py: preserve architecture facts for receiving AI without granting new authority.
p = Path("src/graft_plus/decision.py")
text = p.read_text()
text = text.replace('        "schema_version": "1.2",\n', '        "schema_version": "1.3",\n', 1)
old = '''            "deployment_fact_count": residuals.get("deployment_fact_count") or 0,\n            "deployment_fact_counts_by_kind": residuals.get("deployment_fact_counts_by_kind") or {},\n'''
new = '''            "deployment_fact_count": residuals.get("deployment_fact_count") or 0,\n            "deployment_fact_counts_by_kind": residuals.get("deployment_fact_counts_by_kind") or {},\n            "subsystem_count": residuals.get("subsystem_count") or 0,\n            "subsystem_direct_member_counts": residuals.get("subsystem_direct_member_counts") or {},\n            "cross_language_subsystem_count": residuals.get("cross_language_subsystem_count") or 0,\n            "cross_language_subsystems": residuals.get("cross_language_subsystems") or [],\n            "build_definition_count": residuals.get("build_definition_count") or 0,\n            "build_definition_counts_by_system": residuals.get("build_definition_counts_by_system") or {},\n            "build_input_edge_count": residuals.get("build_input_edge_count") or 0,\n            "governance_boundary_count": residuals.get("governance_boundary_count") or 0,\n            "governance_boundary_counts_by_kind": residuals.get("governance_boundary_counts_by_kind") or {},\n            "source_provenance_counts": residuals.get("source_provenance_counts") or {},\n'''
if old not in text:
    raise SystemExit("decision architecture facts marker missing")
p.write_text(text.replace(old, new, 1))
