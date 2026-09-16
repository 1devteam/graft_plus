"""Select proof from impact. Bundles come from the subject overlay, never hardcoded products."""

from __future__ import annotations

from typing import Any


def select_proofs(impact: dict[str, Any], overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    overlay = overlay or {}
    invariant_ids = {
        str(item.get("id"))
        for item in (impact.get("relevant_invariants") or overlay.get("invariants") or [])
        if item.get("id")
    }
    risk_ids = {str(item.get("id")) for item in (impact.get("risk_domains") or []) if item.get("id")}
    selected = []
    for bundle in overlay.get("proof_bundles") or []:
        inv = set(bundle.get("invariants") or ())
        risk = set(bundle.get("risk_domains") or ())
        if inv.intersection(invariant_ids) or risk.intersection(risk_ids):
            selected.append(bundle)

    impacted_tests = sorted(
        {
            str(item if isinstance(item, str) else item.get("source") or item.get("id") or "")
            for item in (impact.get("impacted_tests") or [])
        }
        - {""}
    )
    required_tests = sorted({str(t) for b in selected for t in (b.get("tests") or [])}.union(impacted_tests))
    required_gates = sorted({str(g) for b in selected for g in (b.get("required_gates") or [])})
    if impact.get("changed_node_count"):
        required_gates = sorted(set(required_gates).union({"unit-tests"}))
    manual_review = []
    if impact.get("unmapped_changed_files"):
        manual_review.append("Review unmapped changed files; the graph does not yet model them.")
    for invariant in impact.get("relevant_invariants") or []:
        status = str(invariant.get("status") or "")
        invariant_id = str(invariant.get("id") or "")
        if status == "known_violation":
            manual_review.append(
                f"Invariant {invariant_id} has a known baseline violation; an acknowledgement is not a repair."
            )
        elif status == "policy_drift":
            manual_review.append(f"Invariant {invariant_id} is recorded as policy drift and requires human review.")
    return {
        "schema_version": "1.0",
        "selected_bundles": [
            {
                "id": b.get("id"),
                "title": b.get("title"),
                "matched_invariants": sorted(set(b.get("invariants") or ()).intersection(invariant_ids)),
                "matched_risk_domains": sorted(set(b.get("risk_domains") or ()).intersection(risk_ids)),
            }
            for b in selected
        ],
        "required_tests": required_tests,
        "required_gates": required_gates,
        "review_gates": sorted({str(g) for b in selected for g in (b.get("review_gates") or [])}),
        "manual_review": manual_review,
        "metrics": {
            "selected_bundle_count": len(selected),
            "required_test_count": len(required_tests),
            "required_gate_count": len(required_gates),
        },
        "note": "Bundles are overlay-supplied. This package has no product-specific proofs.",
    }
