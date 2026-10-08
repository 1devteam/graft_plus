# Reading a G.R.A.F.T.+ pack

Start with `00-AI-READ-FIRST.md`. It gives the receiving AI a conservative read
order and evidence rules. Then use `graft-plus-receipt.json` to confirm the
subject revision and `dependency-graph.ascii.v1.txt` as the primary topology
surface. Use `dependency-graph.v1.json` only when exact evidence anchors or
fields omitted from the fast ASCII projection are needed.

The graph is a source-backed map, not a source dump and not an adjudicator. It
records system-bearing files, declared intent documents, modules, tests,
packages, entrypoints, dependencies, routes, data tables, contracts, egress,
and the relationships an adapter can prove. Files in a recognized source
language without a relationship adapter remain visible as `file:*` nodes with
`relationship_status: inventory_only`; they are also listed under
`facts.relationship_unparsed_files`.

Language adapters cover Python; JavaScript, TypeScript, and CommonJS; shell
and Bats; Go; Rust; Ruby; PHP; C and C++; Java, Kotlin, and Scala; C#; Lua;
Elixir; and Swift. Resolution remains language-appropriate: for example, Go
imports target declared repository packages, JVM imports target exact declared
symbols, and Swift build-module imports remain unresolved unless the source
tree proves their target.

Schema 1.5 added `facts.relationship_boundaries`. Each row names the
source file, line, language, evidence, and reason for a relationship that
requires build or runtime context. The ledger covers dynamic loading,
wildcard imports, dependency injection, router composition, generated source,
code-generation declarations, and build-module mappings. `declared` rows are
source-visible facts; `unresolved` rows identify the exact next inspection
needed. Neither kind is converted into a speculative edge.

Schema 1.6 adds bounded `evidence_anchor` objects to source-backed nodes and
edges. Anchors name the source, start and end lines, symbol when known,
detector, and whether the location is line- or file-precise. It also parses
declarations and exact imports in Proto, GraphQL, SQL, and Avro sources;
records literal source consumers; and maps configuration-key names plus
deployment structure without retaining configuration values or secrets.

Edges use consumer-to-dependency direction. A reverse walk therefore answers
"what can this change affect?" and a forward walk answers "what does this
piece depend on?" Test edges identify directly relevant tests. Semantic edges
connect source modules to routes, tables, contracts, migrations, and egress
sinks. Every emitted edge endpoint must resolve to exactly one node.

Intent is kept honest in two layers:

- Generated facts identify manifests, READMEs, architecture decisions, and
  plan/specification documents without claiming that their contents are true.
- A reviewed overlay may add subject-specific jobs, artifacts, inputs,
  actions, authority boundaries, invariants, and proof bundles. Those concepts
  are not guessed from names.

Function topology is participation-based. Python functions are emitted when
they participate in an exact local or imported call, direct test import, route
declaration, or entrypoint convention. Repository-relative `function_roots`
in the overlay may deliberately retain every top-level function in a selected
composition root. Unrelated isolated helpers stay out of the artifact.

The remaining factual sidecars answer narrower questions:

- `graph-change-set.v1.json`: requested git refs, exact resolved SHAs, changed
  files, direct source-to-node mappings, and unmapped changed files. It contains
  no transitive reachability or test/proof selection.
- `graph-completeness-report.json`: instrument integrity, stale evidence,
  parser-coverage residuals, unresolved boundaries, and acknowledged findings.
- `graft-plus-receipt.json`: subject revision, artifact inventory, and the
  instrument-integrity-only status.

The former impact, proof-manifest, and architecture-decision sidecars are no
longer emitted. Blast radius, proof selection, risk classification, and
architecture disposition belong to the receiving LLM.


`passed` means the emitted map passed its instrument-integrity checks. It does
not grant merge or execution authority, prove runtime behavior, infer router
prefixes, select proof, calculate blast radius, or turn declared intent into fact.


## Schema 1.8 machine-native representation

Schema 1.8 separates architectural truth from high-volume residual evidence.

- `dependency-graph.v1.json` remains the compact core graph. It no longer repeats
  every unresolved reference row inline.
- `graph-unresolved-ledger.v1.json` preserves unresolved-reference evidence
  losslessly using dictionary tables plus integer reference pairs. It also carries
  class counts and bounded high-frequency summaries for fast inspection.

This is a representation optimization, not evidence deletion. The ledger metadata
embedded in the core graph includes a SHA-256 digest of the exact sidecar content.

Schema 1.8 also projects GN build targets as first-class `build_target` nodes.
`BUILD.gn` targets declare source inputs and target dependencies where literal
repository evidence is sufficient. C/C++ quoted includes additionally resolve from
the repository root when that exact file exists, matching common monorepo include
semantics without inventing build state.

Topology summaries such as degree, hubs, crossings, isolated nodes, centrality,
transitive reach, boundary matrices, cycle classification, and semantic
corroboration are not part of the completeness report. They are derivable from
the graph and belong to the receiving LLM rather than instrument self-validation.


## Schema 1.9 canonical metric boundary

Schema 1.9 removes derived topology analytics from the canonical graph metrics.

The graph keeps only shape counts and observation counts produced directly by
reconstruction, such as node/edge totals, parser coverage, unresolved counts,
contract/configuration/build populations, and evidence precision.

The following are no longer canonical graph fields because they are recoverable
from the edge stream:

- edge-type frequency tables;
- ranked fan-in/fan-out lists;
- production fan-in rankings;
- static cycle detection.

The receiving LLM derives these when a question requires them. This avoids
persisting two representations of the same topology and keeps the canonical graph
focused on observed identities, relationships, evidence, and reconstruction facts.

## ASCII topology IR v1

`dependency-graph.ascii.v1.txt` is the primary LLM-facing topology projection.

It is deterministic, ASCII-only, and contains observed graph structure rather than
architectural judgment. It does not calculate blast radius, recommend changes, or
grant authority.

The format uses:

- compact node codes assigned over a deterministic node ordering;
- compact node-type and relation dictionaries;
- node rows carrying full node identity, type, source, and selected structural
  classification fields;
- a fixed-width edge stream where each record is
  `consumer-code + relation-code + dependency-code`;
- a SHA-256 link back to the exact compact JSON graph that produced the projection.

The node/relation codes use a base-62 ASCII alphabet and expand in width only when
the graph population requires it. The edge stream is therefore substantially less
ceremonial than JSON while remaining mechanically decodable.

The ASCII projection is intentionally not a complete duplicate of every evidence
field. G.R.A.F.T. targets a high-value structural surface first; exact evidence
anchors and less frequently needed fields remain in `dependency-graph.v1.json`
for targeted residual lookup.

This split follows the machine-instrument rule: G.R.A.F.T. supplies observed facts
in an efficient representation; the receiving LLM performs dependency reach,
blast-radius, risk, architecture, and change reasoning.
