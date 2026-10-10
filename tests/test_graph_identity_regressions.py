from graft_plus.graph import build_graph


def test_relative_python_import_resolves_without_false_unresolved(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "util.py").write_text("VALUE = 1\n")
    (pkg / "main.py").write_text("from . import util\n")

    graph = build_graph(subject=tmp_path)

    unresolved = {
        (row["from"], row["specifier"])
        for row in graph["facts"]["unresolved_imports"]
    }
    assert ("pkg/main.py", "pkg") not in unresolved
    assert ("pkg/main.py", "pkg.util") not in unresolved
    assert any(
        edge["from"] == "py:pkg.main"
        and edge["to"] == "py:pkg.util"
        and edge["type"] == "imports"
        for edge in graph["edges"]
    )


def test_migration_and_orm_share_table_identity_without_losing_orm_evidence(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "models.py").write_text(
        "class User:\n"
        "    __tablename__ = 'users'\n"
    )
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_users.py").write_text(
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.create_table('users', sa.Column('id', sa.Integer()))\n"
    )

    graph = build_graph(subject=tmp_path)

    tables = [node for node in graph["nodes"] if node["id"] == "db:table:users"]
    assert len(tables) == 1
    assert any(
        edge["from"] == "py:app.models"
        and edge["to"] == "db:table:users"
        and edge["type"] == "defines_table"
        for edge in graph["edges"]
    )
    assert any(
        edge["from"] == "migration:0001_users"
        and edge["to"] == "db:table:users"
        and edge["type"] == "creates_or_alters_table"
        for edge in graph["edges"]
    )


def test_same_local_route_in_different_modules_keeps_distinct_nodes(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    route_source = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/health')\n"
        "def health():\n"
        "    return {'ok': True}\n"
    )
    (app / "public.py").write_text(route_source)
    (app / "admin.py").write_text(route_source)

    graph = build_graph(subject=tmp_path)

    routes = [
        node for node in graph["nodes"]
        if node["type"] == "http_route" and node.get("path") == "/health"
    ]
    assert len(routes) == 2
    assert len({node["id"] for node in routes}) == 2
    assert {node["source"] for node in routes} == {"app/public.py", "app/admin.py"}
    assert all(node["id"].startswith("route-declaration:app.") for node in routes)


def test_route_declaration_and_proven_runtime_route_are_distinct(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "routes.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/tasks')\n"
        "@router.get('/me')\n"
        "def me():\n"
        "    return {'ok': True}\n"
    )
    (app / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.routes import router as task_router\n"
        "app = FastAPI()\n"
        "app.include_router(task_router, prefix='/v1')\n"
    )

    graph = build_graph(subject=tmp_path)
    nodes = {node["id"]: node for node in graph["nodes"]}

    declaration = next(
        node
        for node in graph["nodes"]
        if node["type"] == "http_route" and node.get("source") == "app/routes.py"
    )
    runtime = nodes["runtime-route:GET:/v1/tasks/me"]

    assert declaration["route_identity"] == "declaration"
    assert declaration["path"] == "/me"
    assert runtime["route_identity"] == "runtime-composed"
    assert runtime["path"] == "/v1/tasks/me"
    assert any(
        edge["from"] == declaration["id"]
        and edge["to"] == runtime["id"]
        and edge["type"] == "composes_to"
        for edge in graph["edges"]
    )


def test_repository_owned_overlay_is_auto_discovered_as_fact(tmp_path):
    contracts = tmp_path / "docs" / "contracts"
    contracts.mkdir(parents=True)
    (tmp_path / "app.py").write_text("VALUE = 1\n")
    (contracts / "dependency-graph.overlay.v1.json").write_text(
        '{"nodes":[{"id":"runtime-action:send","type":"runtime_action","source":"app.py"}],'
        '"edges":[],'
        '"invariants":[{"id":"tenant-isolation","status":"enforced","sources":["app.py"]}]}'
    )

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}

    assert "runtime-action:send" in ids
    assert graph["invariants"] == [
        {"id": "tenant-isolation", "status": "enforced", "sources": ["app.py"]}
    ]
    assert graph["semantic_provenance"]["overlay_mode"] == "auto-discovered"


def test_rls_is_explicit_security_boundary(tmp_path):
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_secure.py").write_text(
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.execute('ALTER TABLE tenants ENABLE ROW LEVEL SECURITY')\n"
        "    op.execute('ALTER TABLE tenants FORCE ROW LEVEL SECURITY')\n"
        "    op.execute('CREATE POLICY tenant_policy ON tenants USING (true)')\n"
    )

    graph = build_graph(subject=tmp_path)
    nodes = {node["id"]: node for node in graph["nodes"]}
    boundary = nodes["security-boundary:rls:tenants"]

    assert boundary["boundary_kind"] == "row_level_security"
    assert boundary["enabled"] is True
    assert boundary["forced"] is True
    assert boundary["policies"] == ["tenant_policy"]
    assert any(
        edge["from"] == "db:table:tenants"
        and edge["to"] == boundary["id"]
        and edge["type"] == "rls_enforced"
        for edge in graph["edges"]
    )
