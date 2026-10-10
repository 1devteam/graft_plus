from graft_plus.graph import build_graph


def _edge(graph, source, target, kind):
    return any(
        edge["from"] == source and edge["to"] == target and edge["type"] == kind
        for edge in graph["edges"]
    )


def test_callable_topology_maps_methods_nested_handlers_routes_bindings_and_tests(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "runtime.py").write_text(
        "class Worker:\n"
        "    def complete(self):\n"
        "        return self._rollup()\n\n"
        "    def _rollup(self):\n"
        "        return 1\n\n"
        "def isolated_helper():\n"
        "    return 0\n\n"
        "def register():\n"
        "    def handler():\n"
        "        return Worker().complete()\n"
        "    return ActionDefinition(name='job.complete', handler=handler)\n\n"
        "@router.post('/run')\n"
        "def run_route():\n"
        "    return Worker().complete()\n"
    )
    (tmp_path / "tests" / "test_runtime.py").write_text(
        "from app.runtime import Worker\n\n"
        "def test_complete():\n"
        "    worker = Worker()\n"
        "    assert worker.complete() == 1\n"
    )

    graph = build_graph(subject=tmp_path)
    nodes = {node["id"]: node for node in graph["nodes"]}

    complete = "fn:app.runtime:Worker.complete"
    rollup = "fn:app.runtime:Worker._rollup"
    register = "fn:app.runtime:register"
    handler = "fn:app.runtime:register.handler"
    route_handler = "fn:app.runtime:run_route"

    assert nodes[complete]["type"] == "python_method"
    assert nodes[complete]["owner_class"] == "Worker"
    assert nodes[handler]["type"] == "python_function"
    assert nodes[handler]["enclosing_function"] == "register"
    assert nodes[route_handler]["route_handler"] is True

    assert "fn:app.runtime:isolated_helper" not in nodes
    assert _edge(graph, complete, rollup, "calls_function")
    assert _edge(graph, handler, complete, "calls_function")
    assert _edge(graph, route_handler, complete, "calls_function")

    binding = next(
        node
        for node in graph["nodes"]
        if node["type"] == "callable_binding" and node.get("name") == "job.complete"
    )
    assert binding["constructor"] == "ActionDefinition"
    assert _edge(graph, register, binding["id"], "declares_binding")
    assert _edge(graph, binding["id"], handler, "binds_callable")

    assert _edge(graph, "route:POST /run", route_handler, "handled_by")
    assert _edge(
        graph,
        "test:tests/test_runtime.py",
        complete,
        "tests_function",
    )


def test_callable_root_can_deliberately_retain_methods_and_nested_functions(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "flow.py").write_text(
        "class Flow:\n"
        "    def step(self):\n"
        "        return 1\n\n"
        "def build():\n"
        "    def inner():\n"
        "        return 2\n"
        "    return inner()\n"
    )
    overlay = tmp_path / "overlay.json"
    overlay.write_text('{"function_roots":["app"]}')

    graph = build_graph(subject=tmp_path, overlay_path=overlay)
    ids = {node["id"] for node in graph["nodes"]}

    assert "fn:app.flow:Flow.step" in ids
    assert "fn:app.flow:build" in ids
    assert "fn:app.flow:build.inner" in ids
