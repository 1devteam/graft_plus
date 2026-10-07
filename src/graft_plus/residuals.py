"""Machine-native residual encoding.

Keep the architectural graph compact while preserving unresolved-reference evidence
losslessly in a dictionary-encoded sidecar.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

LEDGER_FILE = "graph-unresolved-ledger.v1.json"


def classify_unresolved_reference(specifier: str, source: str) -> str:
    lowered = specifier.lower()
    source_lower = source.lower()
    if lowered.startswith(("http://", "https://", "chrome:", "chrome-untrusted:", "devtools:", "file:")):
        return "url_or_scheme"
    if specifier.startswith("."):
        return "relative_internal_reference"
    if any(token in source_lower for token in ("/test", "tests/", ".test.", ".spec.", "fixture")):
        return "test_or_fixture_context"
    if any(token in source_lower for token in ("generated", "gen/", "out/", "build/")):
        return "generated_or_build_context"
    if lowered.startswith(("tools.", "tools/", "build.", "build/", "scripts.", "scripts/")):
        return "tooling_or_build_reference"
    return "unresolved_absolute_reference"


def build_unresolved_ledger(rows: list[dict[str, str]]) -> dict[str, Any]:
    pairs = sorted({(str(row.get("specifier") or ""), str(row.get("from") or "")) for row in rows})
    sources = sorted({source for _, source in pairs})
    specifiers = sorted({specifier for specifier, _ in pairs})
    source_index = {value: index for index, value in enumerate(sources)}
    specifier_index = {value: index for index, value in enumerate(specifiers)}

    class_counts: Counter[str] = Counter()
    specifier_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    references: list[list[int]] = []
    for specifier, source in pairs:
        references.append([specifier_index[specifier], source_index[source]])
        class_counts[classify_unresolved_reference(specifier, source)] += 1
        specifier_counts[specifier] += 1
        source_counts[source] += 1

    top_specifiers = [
        {"specifier": value, "count": count}
        for value, count in sorted(specifier_counts.items(), key=lambda item: (-item[1], item[0]))[:128]
    ]
    top_sources = [
        {"source": value, "count": count}
        for value, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))[:128]
    ]
    return {
        "schema_version": "1.0",
        "encoding": "dictionary-pairs-v1",
        "reference_count": len(references),
        "unique_specifier_count": len(specifiers),
        "unique_source_count": len(sources),
        "class_counts": dict(sorted(class_counts.items())),
        "top_specifiers": top_specifiers,
        "top_sources": top_sources,
        "specifier_table": specifiers,
        "source_table": sources,
        "references": references,
    }


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def ledger_metadata(ledger: dict[str, Any]) -> dict[str, Any]:
    payload = canonical_json_bytes(ledger)
    return {
        "file": LEDGER_FILE,
        "schema_version": ledger["schema_version"],
        "encoding": ledger["encoding"],
        "reference_count": ledger["reference_count"],
        "unique_specifier_count": ledger["unique_specifier_count"],
        "unique_source_count": ledger["unique_source_count"],
        "class_counts": ledger["class_counts"],
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def compact_graph(graph: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    facts = dict(graph.get("facts") or {})
    facts.pop("unresolved_imports", None)
    facts["unresolved_reference_ledger"] = ledger_metadata(ledger)
    return {**graph, "facts": facts}


def decode_unresolved_ledger(ledger: dict[str, Any]) -> list[dict[str, str]]:
    specifiers = list(ledger.get("specifier_table") or [])
    sources = list(ledger.get("source_table") or [])
    rows: list[dict[str, str]] = []
    for pair in ledger.get("references") or []:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        specifier_index, source_index = pair
        rows.append(
            {
                "specifier": str(specifiers[int(specifier_index)]),
                "from": str(sources[int(source_index)]),
            }
        )
    return sorted(rows, key=lambda row: (row["specifier"], row["from"]))
