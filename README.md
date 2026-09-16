# G.R.A.F.T.+ (`graft_plus`)

Reconstruction method. It emits a **system map** so an AI can see what already exists.

It replaces the 1devteam.com snapshot ingest. It does not zip the repo. It does not dump source. It is not Ajenda's CI gate.

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

Decipher `graph-architecture-decision.json` first. Then the graph.

See [docs/ARTIFACT.md](docs/ARTIFACT.md).
