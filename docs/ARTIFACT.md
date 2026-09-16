# What the artifact is

G.R.A.F.T.+ reconstructs one existing system (a *subject*) into a pack an AI can review.

It is not a zip of the source tree. It is not Ajenda. It is not merge permission.

Generated inventory is ported from the proven Ajenda graph: modules, tests, imports, migrations, tables, HTTP routes, network egress, CI/docker/manifests. Overlay (ownership, authority, policy) stays residual until a reviewed relationship is attached.

## Pack (in order)

1. `graph-architecture-decision.json` — decipher first. Always `merge_authorization: not-determined`.
2. `dependency-graph.v1.json` — the graph. Nodes tagged `generated` or `overlay`.
3. `graph-completeness-report.json` — integrity plus residuals.
4. `graph-impact-report.json` — blast radius when a git range was given (upstream consumers, downstream dependencies, impacted tests, semantic nodes).
5. `graph-proof-manifest.json` — tests implied by impact. Bundles come from overlay.
6. `graft-plus-receipt.json` — what ran, which SHA.

```bash
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```
