from pathlib import Path

p = Path('tests/test_relationship_boundaries.py')
text = p.read_text()
text = text.replace('assert graph["schema_version"] == "1.6"', 'assert graph["schema_version"] == "1.7"', 1)
old = '    assert first["edges"] == second["edges"] == []\n'
new = '''    assert first["edges"] == second["edges"]\n    # The unresolved dynamic load still must not invent a dependency edge.\n    assert not any(edge["type"] in {"imports", "imports_package", "invokes", "sources"} for edge in first["edges"])\n    assert any(edge["type"] == "member_of_subsystem" for edge in first["edges"])\n'''
if old not in text:
    raise SystemExit('relationship-boundary edge assertion marker missing')
p.write_text(text.replace(old, new, 1))
