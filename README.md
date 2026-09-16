# G.R.A.F.T.+ (`graft_plus`)

Artifact builder. It reconstructs one git revision into a pack an AI can read.

It **replaces the snapshot ingest on 1devteam.com** (`/graft` zip of `GRAFT-MAP.md` + `GRAFT-PACK.json` + `tree/`). It is not Ajenda. It is not Ajenda's CI gate. It is not a plan, lease, or merge grant.

```text
product: G.R.A.F.T.+
package: graft_plus
role: fact-substrate
schema: graft-pack-1
implementsPlan: false
mergeAuthorization: not-determined
grants_execution_authority: false
```

## Run

```bash
pip install -e ".[dev]"
graft-plus reconstruct --subject /path/to/repo --out artifacts/graft-pack
```

Feed `GRAFT-MAP.md` to an AI. If markdown truncates, open `GRAFT-PACK.json` and `tree/` in the zip.

## Pack

- `GRAFT-MAP.md` — reader protocol, joints, then source
- `GRAFT-PACK.json` — machine record (`graft-pack-1`)
- `GRAFT-PACK-{slug}.zip` — map + json + `tree/`
- `graph-architecture-decision.json` — decipher summary (`mergeAuthorization` not-determined)

1devteam.com should host a published pack from this CLI. It should not reconstruct-any-repo in the browser.

Ajenda may be a *subject*. Ajenda's `graft_plus_gate.py` stays Ajenda.
