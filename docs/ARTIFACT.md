# What the artifact is

G.R.A.F.T.+ reconstructs one existing system (a *subject*) into a pack an AI can review.

It is not a zip of the source tree. It is not Ajenda. It is not merge permission.

## Pack (in order)

1. `graph-architecture-decision.json` — decipher first. Disposition of the map. Always `merge_authorization: not-determined`. Residuals are listed here so every layer's gaps show at once.
2. `dependency-graph.v1.json` — generated structure (modules, tests, imports, CI/docker/manifests) plus optional overlay. Nodes are tagged `generated` or `overlay`.
3. `graph-completeness-report.json` — integrity plus residuals (unresolved imports, overlay residual, no git range). Acknowledgements are not repairs.
4. `graph-impact-report.json` — blast radius when a git range was given.
5. `graph-proof-manifest.json` — tests/gates implied by impact. Bundles come from the subject's overlay, never from this package.
6. `graft-plus-receipt.json` — what ran, which SHA.

## Residuals (named, not invented)

- Unresolved imports are facts: the specifier is not in this tree. They are not missing files.
- Overlay stays residual until a reviewed relationship is attached.
- No git range means impact and proof stay empty. That is honest, not a pass.
- Stdlib/runtime imports are not unresolved.

## Point at a public repo

```bash
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```
