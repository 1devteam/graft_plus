# What the artifact is

G.R.A.F.T.+ reconstructs one existing system (a *subject*) into a pack an AI can review.

It is not a zip of the source tree. It is not Ajenda. It is not merge permission.

## Pack (in order)

1. `graph-architecture-decision.json` — decipher first. Disposition of the map. Always `merge_authorization: not-determined`.
2. `dependency-graph.v1.json` — generated structure (modules, tests, imports) plus optional overlay.
3. `graph-completeness-report.json` — named gaps. Acknowledgements are not repairs.
4. `graph-impact-report.json` — blast radius when a git range was given.
5. `graph-proof-manifest.json` — tests/gates implied by impact. Bundles come from the subject's overlay, never from this package.
6. `graft-plus-receipt.json` — what ran, which SHA.

## Point at a public repo

```bash
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```

Or a local tree:

```bash
graft-plus reconstruct --subject /path/to/repo --out artifacts/graft-pack
```

## Overlay (optional, subject-owned)

A subject may supply `docs/contracts/dependency-graph.overlay.v1.json` for relationships imports cannot see, invariants, acknowledgements, and proof bundles. This package ships no Ajenda jobs, leases, HubSpot, or RLS rules.
