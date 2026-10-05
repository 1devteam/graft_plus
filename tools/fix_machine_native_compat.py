from pathlib import Path

p = Path('src/graft_plus/decision.py')
text = p.read_text()
old = '''            "relationship_boundary_count": residuals.get("relationship_boundary_count") or 0,
            "unresolved_relationship_boundary_count": residuals.get("unresolved_relationship_boundary_count") or 0,
            "unresolved_import_count": residuals.get("unresolved_import_count") or 0,
            "unresolved_import_classes": residuals.get("unresolved_import_classes") or {},
            "evidence_precision_counts": residuals.get("evidence_precision_counts") or {},
'''
new = '''            "relationship_boundary_count": residuals.get("relationship_boundary_count") or 0,
            "unresolved_relationship_boundary_count": residuals.get("unresolved_relationship_boundary_count") or 0,
            "relationship_boundary_counts_by_kind": residuals.get("relationship_boundary_counts_by_kind") or {},
            "unresolved_import_count": residuals.get("unresolved_import_count") or 0,
            "unresolved_import_classes": residuals.get("unresolved_import_classes") or {},
            "evidence_precision_counts": residuals.get("evidence_precision_counts") or {},
            "contract_source_count": residuals.get("contract_source_count") or 0,
            "contract_declaration_count": residuals.get("contract_declaration_count") or 0,
            "contract_declaration_counts_by_kind": residuals.get("contract_declaration_counts_by_kind") or {},
            "configuration_key_count": residuals.get("configuration_key_count") or 0,
            "deployment_fact_count": residuals.get("deployment_fact_count") or 0,
            "deployment_fact_counts_by_kind": residuals.get("deployment_fact_counts_by_kind") or {},
'''
if old not in text:
    raise SystemExit('compatibility projection marker missing')
p.write_text(text.replace(old, new, 1))
