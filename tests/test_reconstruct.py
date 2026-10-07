import json
from pathlib import Path

from graft_plus.cli import reconstruct
from graft_plus.decision import decide
from graft_plus.graph import build_graph
from graft_plus.completeness import audit
from graft_plus.impact import analyze_impact

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_subject"


def test_tiny_subject_names_modules_and_tests():
    graph = build_graph(subject=FIXTURE)
    ids = {n["id"] for n in graph["nodes"]}
    assert "py:pkg.core" in ids
    assert "py:pkg" in ids
    assert any(i.startswith("test:") for i in ids)
    assert any(e["type"] == "imports" for e in graph["edges"])
    assert any(e["type"] == "tests" for e in graph["edges"])


def test_decision_never_grants_merge(tmp_path):
    graph = build_graph(subject=FIXTURE)
    completeness = audit(graph)
    impact = analyze_impact(graph, [])
    decision = decide(graph=graph, impact=impact, completeness=completeness)
    assert decision["decision"]["merge_authorization"] == "not-determined"
    assert decision["grants_execution_authority"] is False
    assert decision["implementsPlan"] is False
    assert decision["decision"]["full_ci_required"] is True


def test_cli_writes_decipher_pack(tmp_path):
    out = tmp_path / "pack"
    rc = reconstruct(FIXTURE, out, None, None, None)
    assert rc == 0
    guide = (out / "00-AI-READ-FIRST.md").read_text(encoding="utf-8")
    assert "source-backed reconstruction" in guide
    assert "Proven" in guide
    assert "Inferred" in guide
    assert "Unknown" in guide
    assert "Next inspection" in guide
    assert (out / "graph-architecture-decision.json").exists()
    assert (out / "dependency-graph.v1.json").exists()
    receipt = json.loads((out / "graft-plus-receipt.json").read_text(encoding="utf-8"))
    assert receipt["files"][0] == "00-AI-READ-FIRST.md"
    assert receipt["engine"] == "python-universal-shell"
    provenance = receipt["semantic_provenance"]
    assert provenance["semantic_authority"] == "1devteam/graft_plus"
    assert provenance["canonical_schema_version"] == "1.7"
    assert provenance["website_execution_authority"] == "1devteam/1devteam-web"
    assert provenance["website_synchronization_mode"] == "github-reviewed-manual-port"
    assert provenance["website_runtime_dependency"] == "none"


def test_frozen_negatives_cannot_grant_authority():
    graph = build_graph(subject=FIXTURE)
    completeness = audit(graph)
    completeness = {**completeness, "integrity_pass": True, "unacknowledged_blocking_findings": []}
    impact = analyze_impact(graph, [])
    decision = decide(graph=graph, impact=impact, completeness=completeness)
    assert decision["decision"]["architecture_disposition"] == "review-required"
    assert decision["decision"]["merge_authorization"] == "not-determined"
    assert decision["grants_execution_authority"] is False


def test_artifact_is_reconstruction_not_source_dump(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    names = {p.name for p in out.iterdir()}
    assert "00-AI-READ-FIRST.md" in names
    assert "graph-architecture-decision.json" in names
    assert "dependency-graph.v1.json" in names
    assert "graph-completeness-report.json" in names
    assert "graph-impact-report.json" in names
    assert "graft-plus-receipt.json" in names
    assert "GRAFT-MAP.md" not in names
    assert not (out / "tree").exists()


def test_public_repo_parse():
    from graft_plus.fetch import parse_public_repo
    assert parse_public_repo("octocat/Hello-World") == ("octocat", "Hello-World")


def test_proof_has_no_ajenda_bundles():
    from graft_plus.proof import select_proofs
    src = Path(__file__).resolve().parents[1] / "src"
    text = (src / "graft_plus" / "proof.py").read_text()
    assert "tenant-isolation" not in text
    assert "hubspot" not in text.lower()
    assert "ajenda" not in text.lower()
    manifest = select_proofs({"impacted_tests": ["test:tests/test_reconstruct.py"], "changed_node_count": 1}, {})
    assert manifest["required_tests"] == ["test:tests/test_reconstruct.py"]
    assert manifest["selected_bundles"] == []


def test_cli_writes_proof_manifest(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    assert (out / "graph-proof-manifest.json").exists()


def test_unresolved_and_surfaces_are_named(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "main.py").write_text("import requests\nfrom app import util\n")
    (tmp_path / "app" / "util.py").write_text("VALUE = 1\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='app'\n")
    graph = build_graph(subject=tmp_path)
    ids = {n["id"] for n in graph["nodes"]}
    assert "py:app.main" in ids
    assert "ci:.github/workflows/ci.yml" in ids
    specs = {row["specifier"] for row in graph["facts"]["unresolved_imports"]}
    assert "requests" in specs
    completeness = audit(graph)
    assert completeness["residuals"]["overlay"] == "residual"
    decision = decide(graph=graph, impact={"changed_files": []}, completeness=completeness)
    assert decision["decision"]["merge_authorization"] == "not-determined"


def test_semantic_inventory_from_ajenda_logic(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "api.py").write_text(
        "from fastapi import APIRouter\n"
        "import httpx\n"
        "router = APIRouter()\n"
        "@router.get('/health')\n"
        "def health():\n"
        "    httpx.get('https://example.com/status')\n"
        "    return {'ok': True}\n"
    )
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_init.py").write_text(
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.create_table('users', sa.Column('id', sa.Integer()), sa.Column('email', sa.String()))\n"
    )
    graph = build_graph(subject=tmp_path)
    ids = {n["id"] for n in graph["nodes"]}
    types = {n["type"] for n in graph["nodes"]}
    assert "migration:0001_init" in ids
    assert "db:table:users" in ids
    assert "route:GET /health" in ids
    assert "migration" in types
    assert "database_table" in types
    assert "http_route" in types
    assert "network_egress_sink" in types
    completeness = audit(graph)
    decision = decide(graph=graph, impact={"changed_files": []}, completeness=completeness)
    assert decision["decision"]["merge_authorization"] == "not-determined"
    assert "unresolved_imports" not in completeness["residuals"]
    assert "unresolved_import_count" in completeness["residuals"]


def test_flask_django_express_and_stdlib_are_classified(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "web.py").write_text(
        "import ctypes\n"
        "import binascii\n"
        "import stripe\n"
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/status', methods=['GET', 'POST'])\n"
        "def status():\n"
        "    return 'ok'\n"
        "class Watch:\n"
        "    __tablename__ = 'watches'\n"
    )
    (tmp_path / "app" / "urls.py").write_text("from django.urls import path\nurlpatterns = [path('crm/', views.crm)]\n")
    (tmp_path / "server.js").write_text("router.post('/pay', charge);\n")
    graph = build_graph(subject=tmp_path)
    ids = {n["id"] for n in graph["nodes"]}
    specs = {row["specifier"] for row in graph["facts"]["unresolved_imports"]}
    roots = set(graph["facts"]["unresolved_package_roots"])
    assert "route:GET /status" in ids
    assert "route:POST /status" in ids
    assert "route:ANY crm/" in ids
    assert "route:POST /pay" in ids
    assert "db:table:watches" in ids
    assert "ctypes" not in specs
    assert "binascii" not in specs
    assert "stripe" in specs
    assert "" not in roots



def test_completeness_ratchet_acknowledgement_is_not_repair():
    graph = build_graph(subject=FIXTURE)
    overlay = {
        "findings": [
            {
                "id": "rls-missing:users",
                "blocking": True,
                "classification": "known_violation",
                "summary": "table users lacks RLS",
            }
        ]
    }
    blocked = audit(graph, overlay)
    assert blocked["integrity_pass"] is False
    assert "rls-missing:users" in blocked["unacknowledged_blocking_findings"]
    assert blocked["integrity"]["pass"] is False
    decision = decide(graph=graph, impact={"changed_files": []}, completeness=blocked)
    assert decision["decision"]["architecture_disposition"] == "blocked"
    assert decision["decision"]["merge_authorization"] == "not-determined"

    overlay["acknowledged_findings"] = ["rls-missing:users"]
    known = audit(graph, overlay)
    assert known["integrity_pass"] is True
    assert "rls-missing:users" in known["acknowledged_findings"]
    assert "rls-missing:users" in known["integrity"]["known_violations"]
    finding = next(item for item in known["semantic_findings"] if item["id"] == "rls-missing:users")
    assert finding["acknowledged"] is True
    passed = decide(graph=graph, impact={"changed_files": []}, completeness=known)
    assert passed["decision"]["architecture_disposition"] == "review-required"
    assert "known_violations_visible" in passed["decision"]["review_reasons"]
    assert passed["decision"]["merge_authorization"] == "not-determined"
