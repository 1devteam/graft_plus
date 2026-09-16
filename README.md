# G.R.A.F.T.+ (`graft_plus`)

Reconstruction method extracted from a proven Ajenda pipeline. Project-agnostic. No Ajenda domain logic.

Point it at an existing public repository. It writes a pack an AI can read. 1devteam.com hosts that pack. It does not dump source.

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
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```

Decipher `graph-architecture-decision.json` first.

See [docs/ARTIFACT.md](docs/ARTIFACT.md).
