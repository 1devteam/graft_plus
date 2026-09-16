from graft_plus.graph import build_graph


def _edge(graph, source, target, kind):
    return any(
        edge["from"] == source and edge["to"] == target and edge["type"] == kind
        for edge in graph["edges"]
    )


def test_rust_ruby_php_and_lua_local_relationships(tmp_path):
    (tmp_path / "rust").mkdir()
    (tmp_path / "rust" / "lib.rs").write_text("mod util;\npub fn run() { util::work(); }\n")
    (tmp_path / "rust" / "util.rs").write_text("pub fn work() {}\n")

    (tmp_path / "ruby" / "spec").mkdir(parents=True)
    (tmp_path / "ruby" / "app.rb").write_text("require_relative 'service'\n")
    (tmp_path / "ruby" / "service.rb").write_text("class Service; end\n")
    (tmp_path / "ruby" / "spec" / "app_spec.rb").write_text("require_relative '../app'\n")

    (tmp_path / "php").mkdir()
    (tmp_path / "php" / "index.php").write_text("<?php require_once __DIR__ . '/lib.php';\n")
    (tmp_path / "php" / "lib.php").write_text("<?php function work() {}\n")

    (tmp_path / "lua" / "lib").mkdir(parents=True)
    (tmp_path / "lua" / "main.lua").write_text("local util = require('lib.util')\n")
    (tmp_path / "lua" / "lib" / "util.lua").write_text("return {}\n")

    graph = build_graph(subject=tmp_path)

    assert _edge(graph, "rs:rust/lib.rs", "rs:rust/util.rs", "imports")
    assert _edge(graph, "rb:ruby/app.rb", "rb:ruby/service.rb", "imports")
    assert _edge(graph, "test:ruby/spec/app_spec.rb", "rb:ruby/app.rb", "tests")
    assert _edge(graph, "php:php/index.php", "php:php/lib.php", "imports")
    assert _edge(graph, "lua:lua/main.lua", "lua:lua/lib/util.lua", "imports")


def test_native_jvm_dotnet_and_elixir_declared_relationships(tmp_path):
    (tmp_path / "native").mkdir()
    (tmp_path / "native" / "main.c").write_text('#include "util.h"\nint main(void) { return value(); }\n')
    (tmp_path / "native" / "util.h").write_text("int value(void);\n")

    (tmp_path / "jvm" / "example").mkdir(parents=True)
    (tmp_path / "jvm" / "example" / "A.java").write_text("package example;\nimport example.B;\nclass A {}\n")
    (tmp_path / "jvm" / "example" / "B.java").write_text("package example;\nclass B {}\n")

    (tmp_path / "dotnet").mkdir()
    (tmp_path / "dotnet" / "Program.cs").write_text("using App.Services;\nnamespace App;\nclass Program {}\n")
    (tmp_path / "dotnet" / "Services.cs").write_text("namespace App.Services;\nclass Worker {}\n")

    (tmp_path / "elixir").mkdir()
    (tmp_path / "elixir" / "app.ex").write_text("defmodule App do\n  alias App.Worker\nend\n")
    (tmp_path / "elixir" / "worker.ex").write_text("defmodule App.Worker do\nend\n")

    graph = build_graph(subject=tmp_path)

    assert _edge(graph, "native:native/main.c", "native:native/util.h", "imports")
    assert _edge(graph, "jvm:jvm/example/A.java", "jvm:jvm/example/B.java", "imports")
    assert _edge(graph, "dotnet:dotnet/Program.cs", "dotnet:dotnet/Services.cs", "imports")
    assert _edge(graph, "ex:elixir/app.ex", "ex:elixir/worker.ex", "imports")


def test_swift_is_source_mapped_without_inventing_build_module_resolution(tmp_path):
    (tmp_path / "App.swift").write_text("import Foundation\nimport FeatureKit\nstruct App {}\n")

    graph = build_graph(subject=tmp_path)

    node = next(node for node in graph["nodes"] if node["id"] == "swift:App.swift")
    assert node["type"] == "swift_module"
    assert graph["facts"]["relationship_unparsed_files"] == []
    unresolved = {(row["from"], row["specifier"]) for row in graph["facts"]["unresolved_imports"]}
    assert ("App.swift", "Foundation") not in unresolved
    assert ("App.swift", "FeatureKit") in unresolved


def test_extended_language_graph_has_unique_resolved_endpoints(tmp_path):
    (tmp_path / "main.cpp").write_text('#include "value.hpp"\n')
    (tmp_path / "value.hpp").write_text("int value();\n")

    graph = build_graph(subject=tmp_path)
    ids = [node["id"] for node in graph["nodes"]]

    assert len(ids) == len(set(ids))
    assert all(edge["from"] in set(ids) and edge["to"] in set(ids) for edge in graph["edges"])


def test_rust_ignores_documentation_imports_and_resolves_its_declared_crate(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "benches").mkdir()
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "sample-crate"\nversion = "1.0.0"\n')
    (tmp_path / "src" / "lib.rs").write_text(
        "/*! Example only:\nuse imaginary::Thing;\n*/\n"
        "mod util;\n"
    )
    (tmp_path / "src" / "util.rs").write_text("pub fn value() -> u8 { 1 }\n")
    (tmp_path / "benches" / "bench.rs").write_text(
        "use sample_crate::value;\n"
        "use std::time::Duration;\n"
    )

    graph = build_graph(subject=tmp_path)

    assert _edge(graph, "rs:src/lib.rs", "rs:src/util.rs", "imports")
    assert _edge(graph, "rs:benches/bench.rs", "rs:src/lib.rs", "imports")
    unresolved = {row["specifier"] for row in graph["facts"]["unresolved_imports"]}
    assert "imaginary" not in unresolved
    assert "std" not in unresolved
