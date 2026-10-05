from pathlib import Path

p = Path('src/graft_plus/inventory.py')
text = p.read_text()
marker = '''BUILD_FILES = {
    ".gn",
    "BUILD",
    "BUILD.bazel",
    "BUILD.gn",
    "CMakeLists.txt",
    "DEPS",
    "GNUmakefile",
    "Makefile",
    "MODULE.bazel",
    "SConscript",
    "SConstruct",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "meson.build",
    "meson_options.txt",
}
'''
replacement = '''BUILD_FILES = {
    ".gn",
    "BUILD",
    "BUILD.bazel",
    "BUILD.gn",
    "CMakeLists.txt",
    "Cargo.lock",
    "Cargo.toml",
    "DEPS",
    "GNUmakefile",
    "Gemfile",
    "Makefile",
    "MODULE.bazel",
    "Package.swift",
    "Rakefile",
    "SConscript",
    "SConstruct",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "go.mod",
    "go.sum",
    "meson.build",
    "meson_options.txt",
    "mix.exs",
    "package-lock.json",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
    "settings.gradle.kts",
}
'''
if marker not in text:
    raise SystemExit('build-control marker missing')
p.write_text(text.replace(marker, replacement, 1))
