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
- Python, JavaScript/TypeScript/CommonJS, shell/Bats, Go, Rust, Ruby, PHP,
  C/C++, Java/Kotlin/Scala, C#, Lua, Elixir, and Swift source relationships
- package, workspace, dependency, and entrypoint declarations
- participation-based Python callable topology: functions, methods, nested handlers, calls, direct tests, route ownership, and exact literal callable bindings
- migrations, tables, routes, contracts, network egress, and delivery surfaces
- source-and-line boundary ledger for relationships requiring build or runtime context
- declaration topology for Proto, GraphQL, SQL, and Avro contract sources
- environment-name and deployment-structure topology without secret values
- bounded source/line/symbol evidence anchors on generated facts
- optional overlay (ownership, authority, policy) — residual until attached
- factual changed-file and direct source-to-node mapping when a git range is given
- completeness ratchet (acknowledgement is not a repair)
- instrument-integrity report with unresolved residuals kept visible

```bash
pip install -e ".[dev]"
graft-plus reconstruct --repo owner/repo --out artifacts/graft-pack
```

Give the complete pack to the receiving AI; `00-AI-READ-FIRST.md` tells it how to
interpret the evidence without overstating what static reconstruction proves.
The primary LLM topology surface is `dependency-graph.ascii.v1.txt`; the JSON
graph remains available for exact evidence-anchor lookup. When a git range is
requested, `graph-change-set.v1.json` supplies only direct change seeds. The
receiving LLM calculates reach, proof strategy, risk, and architecture itself.
See [docs/ARTIFACT.md](docs/ARTIFACT.md).

## Website authority and synchronization

`1devteam/graft_plus` is the semantic authority for G.R.A.F.T.+ research and reconstruction behavior. The deployed public workbench at `1devteam.com/graft` keeps its execution authority inside `1devteam/1devteam-web` and runs an embedded browser port. The website does not require this repository to be running as a backend service.

Approved semantic changes move to the website through GitHub-reviewed ports. A website port records the canonical reference revision it was compared against, its embedded schema version, and whether semantic parity is actually claimed. A reference SHA is provenance, not proof that the browser port is current.

Cloudflare may host the website, but G.R.A.F.T.+ reconstruction must not require a Cloudflare Worker, tunnel, localhost service, or external graph runtime. The optional HTTP adapter in this repository remains available for development, integration testing, and other explicitly chosen deployments; it is not the authority loop for the public website.

See [docs/DEPLOYMENT_SYNC.md](docs/DEPLOYMENT_SYNC.md) for the cross-repository contract.
