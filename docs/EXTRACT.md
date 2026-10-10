# Extract from Ajenda (`6f81113`)

## Into `graft_plus` (this repo)

Generic reconstruction:

- static Python / TypeScript / test import graph
- optional overlay JSON (subject-supplied)
- git-range impact against the graph
- completeness (undefined edge endpoints, overlay integrity)
- architecture decision writer (`merge_authorization` always `not-determined`)
- CLI runner that emits the decipher pack

Source lineage (do not copy Ajenda-only coupling):

- `scripts/validation/build_dependency_graph.py` (static layers)
- `scripts/validation/graph_function_inventory.py` (genericized; no mission_composition hardcode)
- `scripts/validation/graph_impact_analysis.py` (path → node impact)
- `scripts/validation/graph_completeness_audit.py` (integrity)
- `scripts/validation/graph_architecture_decision.py` (decision compose)
- overlay *schema* (not Ajenda's full overlay instance)

## Stay in Ajenda

- `scripts/validation/mission_contract_gate.py`
- Ajenda-specific runtime adjudication, action selection, instantiated applicability, and mission-instance integrity
- Ajenda catalog contents, resolver policy, and product-specific runtime binding rules
- Ajenda-specific semantic findings/adjudication

Generic source-backed declaration *shapes* proven by those inventories now belong in `graft_plus`: literal job/action/input/artifact declarations, action input-model/provider/side-effect/credential fields, RLS/security facts, direct egress facts, and other repository-derived observations. Product catalogs and decisions do not.
- `graft_plus_gate.py` as Ajenda's wrapper (may later *call* this package)
- job catalog, capability resolver, composition engine
- `docs/contracts/dependency-graph.overlay.v1.json` Ajenda instance

This package is the 1devteam.com pack builder. It is not Ajenda's merge/CI gate. Ajenda may run reconstruct as a *subject* later; do not grow Ajenda graph scripts as the product.
