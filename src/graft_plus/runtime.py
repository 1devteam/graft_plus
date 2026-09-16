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

RUNTIME_ROOTS = set(getattr(sys, "stdlib_module_names", ())) | _EXTRA


def is_runtime(specifier: str) -> bool:
    if not specifier or specifier.startswith("."):
        return True
    if specifier.startswith("node:"):
        return True
    root = specifier.split(".")[0].split("/")[0]
    return root in RUNTIME_ROOTS
