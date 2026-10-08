import json

from graft_plus.completeness import audit
from graft_plus.graph import build_graph


def _edge(graph, source, target, kind):
    return next(
        edge
        for edge in graph["edges"]
        if edge["from"] == source and edge["to"] == target and edge["type"] == kind
    )


def test_every_source_backed_fact_has_a_bounded_evidence_anchor(tmp_path):
    (tmp_path / "app.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'ok': True}\n"
    )

    graph = build_graph(subject=tmp_path)

    route = next(node for node in graph["nodes"] if node["type"] == "http_route")
    assert route["evidence_anchor"] == {
        "source": "app.py",
        "start_line": 3,
        "end_line": 5,
        "symbol": "health",
        "detector": "python_ast",
        "precision": "line",
    }
    edge = _edge(graph, "py:app", route["id"], "exposes_route")
    assert edge["evidence_anchor"]["start_line"] == 3
    assert edge["evidence_anchor"]["precision"] == "line"
    for node in graph["nodes"]:
        if node.get("source") and (tmp_path / node["source"]).is_file():
            assert node["evidence_anchor"]["start_line"] >= 1
            assert node["evidence_anchor"]["end_line"] >= node["evidence_anchor"]["start_line"]
    assert all("evidence_anchor" in edge for edge in graph["edges"])


def test_function_topology_is_automatic_but_participation_based(tmp_path):
    app = tmp_path / "app"
    tests = tmp_path / "tests"
    app.mkdir()
    tests.mkdir()
    (app / "__init__.py").write_text("")
    (app / "helpers.py").write_text(
        "def used():\n    return 1\n\n"
        "def isolated():\n    return 2\n"
    )
    (app / "api.py").write_text(
        "from fastapi import APIRouter\n"
        "from app.helpers import used\n"
        "router = APIRouter()\n"
        "@router.get('/value')\n"
        "def value():\n"
        "    return used()\n"
    )
    (tests / "test_api.py").write_text("from app.api import value\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}

    assert "fn:app.helpers:used" in ids
    assert "fn:app.api:value" in ids
    assert "fn:app.helpers:isolated" not in ids
    call = _edge(graph, "fn:app.api:value", "fn:app.helpers:used", "calls_function")
    assert call["evidence_anchor"]["start_line"] == 6
    route = next(node for node in graph["nodes"] if node.get("path") == "/value")
    _edge(graph, route["id"], "fn:app.api:value", "handled_by")
    _edge(graph, "test:tests/test_api.py", "fn:app.api:value", "tests_function")


def test_function_calls_require_exact_local_or_imported_identity(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text("def resolve():\n    return 1\n")
    (pkg / "flow.py").write_text(
        "from pathlib import Path\n"
        "from .helpers import resolve\n\n"
        "def run():\n"
        "    Path('.').resolve()\n"
        "    return resolve()\n"
    )

    graph = build_graph(subject=tmp_path)
    calls = [edge for edge in graph["edges"] if edge["type"] == "calls_function"]

    assert len(calls) == 1
    assert calls[0]["from"] == "fn:pkg.flow:run"
    assert calls[0]["to"] == "fn:pkg.helpers:resolve"
    assert calls[0]["evidence_anchor"]["start_line"] == 6


def test_contract_declarations_imports_and_literal_consumers(tmp_path):
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "common.proto").write_text('syntax = "proto3";\nmessage Id { string value = 1; }\n')
    (schemas / "api.proto").write_text(
        'syntax = "proto3";\nimport "common.proto";\nmessage User {}\nservice Users { rpc Get (User) returns (User); }\n'
    )
    (schemas / "api.graphql").write_text(
        "type User { id: ID! }\n"
        "type Query {\n  user(id: ID!): User\n}\n"
    )
    (schemas / "schema.sql").write_text("CREATE TABLE public.users (id integer);\nCREATE VIEW active_users AS SELECT * FROM public.users;\n")
    (schemas / "event.avsc").write_text(json.dumps({"type": "record", "name": "UserCreated", "fields": []}))
    (tmp_path / "client.py").write_text("# 'schemas/common.proto' is documentation only\nSCHEMA = 'schemas/api.proto'\n")

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}

    assert "contract:protobuf_message:schemas/api.proto:User" in ids
    assert "contract:protobuf_service:schemas/api.proto:Users" in ids
    assert "contract:protobuf_rpc:schemas/api.proto:Get" in ids
    assert "contract:graphql_operation:schemas/api.graphql:Query.user" in ids
    assert "contract:sql_table:schemas/schema.sql:public.users" in ids
    assert "contract:sql_view:schemas/schema.sql:active_users" in ids
    assert "contract:avro_record:schemas/event.avsc:UserCreated" in ids
    _edge(graph, "file:schemas/api.proto", "file:schemas/common.proto", "imports_contract")
    _edge(graph, "py:client", "file:schemas/api.proto", "consumes_contract")
    assert not any(
        edge["from"] == "py:client"
        and edge["to"] == "file:schemas/common.proto"
        and edge["type"] == "consumes_contract"
        for edge in graph["edges"]
    )
    assert graph["metrics"]["contract_source_count"] == 5
    assert graph["metrics"]["contract_declaration_count"] >= 8


def test_configuration_and_deployment_map_names_without_values(tmp_path):
    (tmp_path / ".env.example").write_text("DATABASE_URL=postgres://secret.example/db\nFEATURE_BETA=true\n")
    (tmp_path / "app.py").write_text(
        "import os\n"
        "database = os.getenv('DATABASE_URL')\n"
        "beta = os.environ['FEATURE_BETA']\n"
    )
    (tmp_path / "server.js").write_text("const port = process.env.PORT\n")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  api:\n"
        "    command: python app.py\n"
        "    ports:\n"
        "      - '8000:8000'\n"
        "    environment:\n"
        "      DATABASE_URL: hidden\n"
        "    healthcheck:\n"
        "      test: curl localhost\n"
    )
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12\n"
        "ENV WORKERS=2\n"
        "EXPOSE 8000/tcp\n"
        "CMD [\"python\", \"app.py\"]\n"
    )

    graph = build_graph(subject=tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    serialized = json.dumps(graph, sort_keys=True)

    assert {"config:key:DATABASE_URL", "config:key:FEATURE_BETA", "config:key:PORT", "config:key:WORKERS"} <= ids
    _edge(graph, "py:app", "config:key:DATABASE_URL", "reads_config")
    _edge(graph, "js:server.js", "config:key:PORT", "reads_config")
    _edge(graph, "file:.env.example", "config:key:FEATURE_BETA", "declares_config")
    assert "postgres://secret.example/db" not in serialized
    assert "DATABASE_URL: hidden" not in serialized
    assert {row["kind"] for row in graph["facts"]["deployment_facts"]} >= {
        "services",
        "command",
        "ports",
        "healthcheck",
        "env",
        "expose",
        "cmd",
    }
    assert any(row.get("kind") == "port" and row.get("name") == "8000:8000" for row in graph["facts"]["deployment_facts"])
    completeness = audit(graph, subject=tmp_path)
    assert completeness["residuals"]["configuration_key_count"] == 4
    assert completeness["residuals"]["deployment_fact_count"] >= 7
    assert (
        completeness["residuals"]["evidence_precision_counts"]
        == graph["metrics"]["evidence_precision_counts"]
    )
    assert completeness["integrity_pass"] is True


def test_lexical_boundary_detector_ignores_comments_and_string_bodies(tmp_path):
    (tmp_path / "app.js").write_text(
        "const example = `require(fakeTarget)`\n"
        "/* import(blockComment) */\n"
        "// container.resolve(commentToken)\n"
        "const staticPlugin = require('known-plugin')\n"
        "const plugin = import(pluginName)\n"
        "app.use('/v1', router)\n"
    )

    graph = build_graph(subject=tmp_path)
    rows = [row for row in graph["facts"]["relationship_boundaries"] if row["source"] == "app.js"]

    assert [(row["kind"], row["line"], row["detector"]) for row in rows] == [
        ("dynamic_load", 5, "lexical_pattern"),
        ("route_composition", 6, "lexical_pattern"),
    ]


def test_shell_configuration_excludes_local_variables_and_deduplicates_reads(tmp_path):
    (tmp_path / "run.sh").write_text(
        "#!/usr/bin/env bash\n"
        "LOCAL_COLOR=blue\n"
        "echo \"$LOCAL_COLOR\"\n"
        "TOKEN=\"${TOKEN:-}\"\n"
        "echo \"$TOKEN\"\n"
        "echo \"$TOKEN\"\n"
    )

    graph = build_graph(subject=tmp_path)
    keys = {node["id"] for node in graph["nodes"] if node["type"] == "configuration_key"}
    reads = [edge for edge in graph["edges"] if edge["type"] == "reads_config"]

    assert "config:key:LOCAL_COLOR" not in keys
    assert "config:key:TOKEN" in keys
    assert len([edge for edge in reads if edge["to"] == "config:key:TOKEN"]) == 1
