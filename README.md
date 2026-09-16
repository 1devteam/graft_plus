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

- complete system-bearing file and declared-intent inventory
- Python, JavaScript/TypeScript/CommonJS, shell, and Bats module/test relationships
- package, workspace, dependency, and entrypoint declarations
- optional function/call/test-function topology for overlay-selected composition roots
- migrations, tables, routes, contracts, network egress, and delivery surfaces
- optional overlay (ownership, authority, policy) — residual until attached
- blast radius when a git range is given
- completeness ratchet (acknowledgement is not a repair)
- architecture decision that never grants merge

```bash
pip install -e ".[dev]"
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```

Decipher `graph-architecture-decision.json` first. See [docs/ARTIFACT.md](docs/ARTIFACT.md).

## Stateless web boundary

The optional HTTP adapter runs this same canonical engine for the public
1devteam.com workbench:

```bash
pip install -e ".[service]"
GRAFT_ALLOWED_ORIGINS=https://1devteam.com,https://www.1devteam.com graft-plus-api
```

`POST /v1/reconstruct` accepts a public GitHub `repository` and optional
`ref`, then returns the validated pack as a ZIP. Source and artifacts exist
only in a bounded temporary workspace and are removed before the response is
sent. Responses are `no-store`; the service has no account, history, plan, or
merge-authority surface.
