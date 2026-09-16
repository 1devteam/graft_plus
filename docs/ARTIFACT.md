# Reading a G.R.A.F.T.+ pack

Start with `AI-RECEIVER.md`. It gives the receiving AI a conservative read
order, question patterns, evidence rules, and a required Proven / Inferred /
Unknown / Next inspection answer discipline. Then use
`graft-plus-receipt.json` to confirm the subject revision and
`dependency-graph.v1.json` for the evidence behind the summary.

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

The remaining reports answer narrower questions:

- `graph-impact-report.json`: changed nodes, upstream consumers, downstream
  dependencies, semantic reach, and impacted tests for a requested git range.
- `graph-completeness-report.json`: endpoint integrity, stale evidence,
  parser-coverage residuals, boundaries, cycles, and acknowledged findings.
- `graph-proof-manifest.json`: overlay-selected proof obligations; it never
  invents product-specific gates.
- `graft-plus-receipt.json`: subject revision and reconstruction status.

`clear` means the emitted map passed its integrity checks. It does not grant
merge or execution authority, prove runtime behavior, infer router prefixes,
or turn declared intent into fact.
