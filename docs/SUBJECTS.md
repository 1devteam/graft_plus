# Subjects

G.R.A.F.T.+ maps a *subject*. The subject is not this package.

| Subject | Repo | Role |
|---|---|---|
| This package | `1devteam/graft_plus` | Builder. Reconstruct itself in CI. |
| Ajenda | `1devteam/ajenda-ai` | First reconstruction subject. Keeps mission-contract, job catalog, runtime inventories. |
| Omnipath v2 | later | Second reconstruction subject. |
| 1devteam.com | `1devteam/1devteam-web` | Hosts a published pack. Not the builder. Snapshot ingest on `/graft` is not G.R.A.F.T.+. |

Ajenda CI should eventually run:

```bash
graft-plus reconstruct --subject . --overlay docs/contracts/dependency-graph.overlay.v1.json --out artifacts/graft-pack
```

That wiring is an Ajenda change. Do not grow Ajenda's graph scripts instead of calling this package.

`merge_authorization` stays `not-determined` on every subject.
