import json
from pathlib import Path

from graft_plus.cli import reconstruct
from graft_plus.completeness import audit
from graft_plus.fetch import parse_public_repo
from graft_plus.graph import build_graph

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_subject"


def test_tiny_subject_names_modules_and_tests():
    graph = build_graph(subject=FIXTURE)
    ids = {node["id"] for node in graph["nodes"]}
    assert "py:pkg.core" in ids
    assert "py:pkg" in ids
    assert any(node_id.startswith("test:") for node_id in ids)
    assert any(edge["type"] == "imports" for edge in graph["edges"])
    assert any(edge["type"] == "tests" for edge in graph["edges"])


def test_cli_receipt_never_grants_reasoning_or_execution_authority(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    receipt = json.loads((out / "graft-plus-receipt.json").read_text(encoding="utf-8"))

    assert receipt["status_scope"] == "instrument-integrity-only"
    assert receipt["merge_authorization"] == "not-determined"
    assert receipt["grants_execution_authority"] is False
    assert receipt["implementsPlan"] is False
    assert set(receipt["does_not_compute"]) >= {
        "blast_radius",
        "proof_selection",
        "risk_classification",
        "architecture_disposition",
        "change_recommendation",
    }


def test_cli_writes_fact_pack(tmp_path):
    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0

    guide = (out / "00-AI-READ-FIRST.md").read_text(encoding="utf-8")
    assert "G.R.A.F.T.+ is a fact instrument" in guide
    assert "The receiving LLM owns those calculations and judgments." in guide

    expected = {
        "00-AI-READ-FIRST.md",
        "dependency-graph.ascii.v1.txt",
        "dependency-graph.v1.json",
        "graph-change-set.v1.json",
        "graph-unresolved-ledger.v1.json",
        "graph-completeness-report.json",
        "graft-plus-receipt.json",
    }
    names = {path.name for path in out.iterdir()}
    assert names == expected

    change_set = json.loads((out / "graph-change-set.v1.json").read_text(encoding="utf-8"))
    assert change_set["role"] == "factual-change-set"
    assert change_set["requested"] is False

    receipt = json.loads((out / "graft-plus-receipt.json").read_text(encoding="utf-8"))
    assert receipt["files"][0] == "00-AI-READ-FIRST.md"
    assert receipt["engine"] == "python-universal-shell"
    assert receipt["change_set"] == "graph-change-set.v1.json"

    provenance = receipt["semantic_provenance"]
    assert provenance["semantic_authority"] == "1devteam/graft_plus"
    assert provenance["canonical_schema_version"] == "1.14"
    assert provenance["website_execution_authority"] == "1devteam/1devteam-web"
    assert provenance["website_synchronization_mode"] == "github-reviewed-manual-port"
    assert provenance["website_runtime_dependency"] == "none"


def test_legacy_reasoning_modules_and_sidecars_are_removed(tmp_path):
    src = Path(__file__).resolve().parents[1] / "src" / "graft_plus"
    assert not (src / "impact.py").exists()
    assert not (src / "proof.py").exists()
    assert not (src / "decision.py").exists()

    out = tmp_path / "pack"
    assert reconstruct(FIXTURE, out, None, None, None) == 0
    for name in (
        "graph-impact-report.json",
        "graph-proof-manifest.json",
        "graph-architecture-decision.json",
    ):
        assert not (out / name).exists()


def test_public_repo_parse():
    assert parse_public_repo("octocat/Hello-World") == ("octocat", "Hello-World")


def test_unresolved_and_surfaces_are_named(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "main.py").write_text("import requests\nfrom app import util\n")
    (tmp_path / "app" / "util.py").write_text("VALUE = 1\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='app'\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    assert "py:app.main" in ids
    assert "ci:.github/workflows/ci.yml" in ids

    specs = {row["specifier"] for row in graph["facts"]["unresolved_imports"]}
    assert "requests" in specs

    completeness = audit(graph)
    assert completeness["residuals"]["overlay"] == "residual"
    assert completeness["residuals"]["unresolved_import_count"] >= 1


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
    ids = {node["id"] for node in graph["nodes"]}
    types = {node["type"] for node in graph["nodes"]}
    assert "migration:0001_init" in ids
    assert "db:table:users" in ids
    assert any(
        node["type"] == "http_route"
        and node.get("method") == "GET"
        and node.get("path") == "/health"
        for node in graph["nodes"]
    )
    assert "migration" in types
    assert "database_table" in types
    assert "http_route" in types
    assert "network_egress_sink" in types

    completeness = audit(graph)
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
    (tmp_path / "app" / "urls.py").write_text(
        "from django.urls import path\nurlpatterns = [path('crm/', views.crm)]\n"
    )
    (tmp_path / "server.js").write_text("router.post('/pay', charge);\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    specs = {row["specifier"] for row in graph["facts"]["unresolved_imports"]}
    roots = set(graph["facts"]["unresolved_package_roots"])

    route_keys = {
        (node.get("method"), node.get("path"), node.get("source"))
        for node in graph["nodes"]
        if node["type"] == "http_route"
    }
    assert ("GET", "/status", "app/web.py") in route_keys
    assert ("POST", "/status", "app/web.py") in route_keys
    assert ("ANY", "crm/", "app/urls.py") in route_keys
    assert ("POST", "/pay", "server.js") in route_keys
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

    overlay["acknowledged_findings"] = ["rls-missing:users"]
    known = audit(graph, overlay)
    assert known["integrity_pass"] is True
    assert "rls-missing:users" in known["acknowledged_findings"]
    assert "rls-missing:users" in known["integrity"]["known_violations"]

    finding = next(
        item for item in known["semantic_findings"] if item["id"] == "rls-missing:users"
    )
    assert finding["acknowledged"] is True
