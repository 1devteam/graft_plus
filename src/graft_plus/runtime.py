"""Runtime/stdlib names. Unresolved imports are third-party or empty, not these."""

from __future__ import annotations

import sys

_EXTRA = {
    "__future__",
    "_thread",
    "builtins",
    "main",
    "pkgutil",
    "posixpath",
    "ntpath",
    "genericpath",
}

_NODE_BUILTINS = {
    "assert",
    "async_hooks",
    "buffer",
    "child_process",
    "cluster",
    "console",
    "crypto",
    "dgram",
    "diagnostics_channel",
    "dns",
    "domain",
    "events",
    "fs",
    "http",
    "http2",
    "https",
    "module",
    "net",
    "os",
    "path",
    "perf_hooks",
    "process",
    "punycode",
    "querystring",
    "readline",
    "repl",
    "stream",
    "string_decoder",
    "sys",
    "timers",
    "tls",
    "trace_events",
    "tty",
    "url",
    "util",
    "v8",
    "vm",
    "wasi",
    "worker_threads",
    "zlib",
}

RUNTIME_ROOTS = set(getattr(sys, "stdlib_module_names", ())) | _EXTRA | _NODE_BUILTINS


def is_runtime(specifier: str) -> bool:
    if not specifier or specifier.startswith("."):
        return True
    if specifier.startswith("node:"):
        return True
    root = specifier.split(".")[0].split("/")[0]
    return root in RUNTIME_ROOTS
