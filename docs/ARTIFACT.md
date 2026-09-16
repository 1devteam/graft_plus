# What the artifact is

G.R.A.F.T.+ writes a reconstruction pack. An AI reviews it to see what already exists.

It is not a zip of the source tree. That snapshot ingest on 1devteam.com is what this builder replaces.

## The pack

Hand these files to an AI, in this order:

1. `graph-architecture-decision.json` — decipher this first. Disposition of the map. Always `merge_authorization: not-determined`.
2. `dependency-graph.v1.json` — inventory: modules, tests, imports, optional overlay.
3. `graph-completeness-report.json` — named gaps and integrity.
4. `graph-impact-report.json` — blast radius when a git range was given.
5. `graft-plus-receipt.json` — what ran, against which SHA.

## Not in the pack

- The subject's source (`tree/`, `GRAFT-MAP.md` file bodies, snapshot zip)
- A plan or next-slice recommendation
- Merge permission, lease, or execution authority
- Ajenda job catalog, abilities, or runtime admission
- Overlay invented without evidence
