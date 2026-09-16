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
