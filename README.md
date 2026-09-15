# G.R.A.F.T.+ (`graft_plus`)

Reconstruction method. It emits a **system map** so an AI can see what already exists before it builds.

It is not Ajenda. It is not 1devteam.com. It is not a workbench, catalog job, plan, lease, or merge grant.

```text
product: G.R.A.F.T.+
package: graft_plus
role: fact-substrate
implementsPlan: false
merge_authorization: not-determined
grants_execution_authority: false
```

## Run

```bash
pip install -e ".[dev]"
graft-plus reconstruct --subject /path/to/repo --out artifacts/graft-pack
```

The decipher pack is `graph-architecture-decision.json`. Read it first. Then the graph.

## What it produces

- `dependency-graph.v1.json` — inventory
- `graph-impact-report.json` — blast radius for a git range (optional)
- `graph-completeness-report.json` — gaps
- `graph-architecture-decision.json` — reviewer summary of the map
- `graft-plus-gate.json` — runner receipt

`clear` on the decision is not permission to merge.

## What stays in Ajenda

Ajenda-specific inventories (job catalog, capability resolver, mission-contract-gate, HubSpot/GTM overlays) stay in `1devteam/ajenda-ai`. This package is the reusable graph core. Ajenda is a *subject*.

See [docs/EXTRACT.md](docs/EXTRACT.md).
