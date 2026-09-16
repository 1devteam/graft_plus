# G.R.A.F.T.+ (`graft_plus`)

Universal reconstruction shell. Point it at a public repository. It writes a pack an AI can read.

Ajenda graph scripts are archived under `docs/origin/` for provenance. They are not the live engine.

```text
product: G.R.A.F.T.+
package: graft_plus
role: fact-substrate
implementsPlan: false
merge_authorization: not-determined
grants_execution_authority: false
```

Live engine:

- generated inventory (modules, tests, imports, migrations, tables, routes, egress, surfaces)
- optional overlay (ownership, authority, policy) — residual until attached
- blast radius when a git range is given
- completeness ratchet (acknowledgement is not a repair)
- architecture decision that never grants merge

```bash
pip install -e ".[dev]"
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```

Decipher `graph-architecture-decision.json` first. See [docs/ARTIFACT.md](docs/ARTIFACT.md).
