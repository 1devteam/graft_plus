# G.R.A.F.T.+ (`graft_plus`)

The graph pipeline copied as-is from [1devteam/ajenda-ai](https://github.com/1devteam/ajenda-ai) `@501d5c95` `scripts/validation/`.

Ajenda-specific catalogs, overlays, and proof bundles are still in those files. Extract them later. Do not rewrite the scripts in place.

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
graft-plus reconstruct --subject /path/to/repo --out artifacts/graft-pack
```

Decipher `graph-architecture-decision.json` first.

Copied scripts live in `src/graft_plus/ajenda_graph/`. Provenance: `src/graft_plus/ajenda_graph/SOURCE.txt`. Ajenda overlay example: `examples/ajenda/`.
