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
- Literal source declarations may generate runtime job/action/input/artifact/provider/credential facts when their fields are statically present in repository code.
- A reviewed overlay may add subject-specific authority boundaries, invariants, and other assertions that cannot be established generically from source. Those assertions remain distinct from generated observations.

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

## Schema 1.10 facts/metrics ownership

Schema 1.10 removes observation counts from `metrics` when the same information is
already owned by a factual producer.

`facts` is now the canonical location for inventory, relationship-boundary,
contract, configuration/deployment, subsystem, build, governance, provenance,
and evidence-precision observations.

`metrics` was narrowed in schema 1.10 and is removed entirely in schema 1.11.

This prevents the same observation from being serialized twice under different
names and keeps the receiving model from reconciling redundant copies of the same
truth.

## Schema 1.11 canonical shape without metrics

Schema 1.11 removes the canonical `metrics` container entirely.

Graph shape is intrinsic to the artifact: node count is `len(nodes)`, edge count is
`len(edges)`, and the ASCII header already carries both counts for stream
validation. Overlay, unresolved, surface, parser, contract, configuration, build,
governance, provenance, and evidence observations remain available from their
canonical node/fact structures.

No observation is retained solely for convenience when it can be recovered
deterministically from canonical facts. Consumers that need counts calculate them
at use time instead of forcing G.R.A.F.T. to serialize duplicate state.

## ASCII topology IR v2 (stable artifact filename)

`dependency-graph.ascii.v1.txt` is the primary LLM-facing topology projection.

It is deterministic, ASCII-only, and contains observed graph structure rather than
architectural judgment. It does not calculate blast radius, recommend changes, or
grant authority.

The current encoder emits a `G2` stream while the decoder remains compatible with legacy `G1` streams.

The format uses:

- compact node codes assigned over a deterministic node ordering;
- compact node-type and relation dictionaries;
- a compact source-path dictionary so repeated source paths are serialized once;
- node rows carrying full node identity, type, a source code, and selected structural
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


## Schema 1.12 callable responsibility topology

Schema 1.12 raises Python callable identity to a first-class factual layer without
turning the graph into a source dump.

The collector still indexes definitions repository-wide, but emits a callable only
when source evidence proves that it participates in system behavior. Participation
includes:

- exact calls between known repository callables;
- `self` / `cls` method calls and simple exact instance-method calls;
- direct test imports and direct test references to imported class methods;
- route decoration and route-to-handler ownership;
- entrypoint conventions;
- exact literal callable bindings such as a constructor call that contains both
  `name="job.complete"` and `handler=handler`;
- explicit `function_roots` selected by a reviewed overlay.

New callable identities preserve qualification:

- top-level function: `fn:<module>:<function>`;
- class method: `fn:<module>:<Class.method>` with node type `python_method`;
- nested function: `fn:<module>:<outer.inner>`.

Exact literal registration is represented as a `callable_binding` node. The
declaring module/callable points to the binding with `declares_binding`; the
binding points to the resolved callable with `binds_callable`.

A callable binding is declaration evidence only. It does not prove that the
registration is activated, reachable at runtime, authorized, invoked, or safe.
Those conclusions remain with the receiving LLM and runtime proof.

The ASCII topology projection needs no special-case encoding for schema 1.12.
The new node and relation types flow through the existing deterministic type and
relation dictionaries, so callable responsibility topology is available on the
primary LLM surface without duplicating evidence anchors.


## Schema 1.13 observer fidelity

Schema 1.13 increases source-backed visibility without moving judgment into the instrument.

Route identity is split into two factual layers:

- `route-declaration:<module-or-source>:<METHOD>:<relative-path>@L<line>` preserves every declaration independently, even when two modules declare the same method/path;
- `runtime-route:<METHOD>:<fully-composed-path>` is emitted only when static router composition can be proven from explicit router/application construction and `include_router` relationships;
- `composes_to` connects declaration identity to proven runtime identity.

Dependency injection now distinguishes exact source declarations from unresolved container lookup. A source form such as `Depends(get_db)` remains a declared boundary and, when `get_db` resolves to a repository callable, emits `injects_dependency`. Dynamic token/container selection remains unresolved.

Exact callable bindings retain source-declared keyword metadata such as provider, input model, side-effect class, and credential requirement. These fields are declaration evidence only; they do not imply activation, authorization, runtime reachability, invocation, or safety.

Repeated callable/test/DI observations no longer duplicate topology edges. One `(from,to,type)` edge carries `occurrences` and a lossless bounded observation list when multiple source locations prove the same relationship.

When no explicit overlay argument is supplied, the engine may discover a repository-owned reviewed overlay at one of the conventional paths:

- `docs/contracts/dependency-graph.overlay.v1.json`
- `.graft/dependency-graph.overlay.v1.json`
- `.graft/overlay.json`

This is not inferred policy. It is explicit repository content and remains an overlay layer distinct from generated observations.

RLS declarations are additionally projected as `security_boundary` nodes with `rls_enforced` relationships. Source-level network calls are named `direct_network_egress` to distinguish raw observed egress from any separately declared egress authority.

The primary ASCII artifact keeps its stable filename but schema 1.13 emits a `G2` topology stream. `G2` interns source paths in an `S<code>=<path>` dictionary; node rows reference source codes. This preserves the same topology while reducing repeated path text. The decoder remains backward-compatible with `G1`.

None of these additions calculate blast radius, select proof, classify risk, recommend architecture, authorize execution, or authorize merge. They only expose more repository reality.


## Schema 1.14 literal runtime declaration topology

Schema 1.14 ports the remaining generic factual layer learned from Ajenda's runtime-contract graph without importing Ajenda catalogs or adjudication.

When Python source contains statically literal contract declarations, the engine may emit:

- `business_job` nodes from declarations that explicitly name required inputs, produced outputs, or candidate actions;
- `runtime_action` nodes from exact callable bindings that declare action-like runtime contract fields;
- `runtime_input` and `runtime_artifact` nodes;
- `runtime_input_contract`, `runtime_provider`, `side_effect_class`, and `credential_requirement` nodes;
- source-backed relationships such as `candidate_action`, `requires_input`, `requires_artifact`, `produced_by`, `declares_input_model`, `declares_side_effect_class`, `uses_provider`, `requires_credential`, and `credential_for_provider`.

The collector recognizes declaration shapes and literal fields, not Ajenda paths, job names, provider names, or business policy. Candidate actions are declarations, not proof of runtime selection. Credential requirements are declarations, not proof of credential availability or authorization. Produced artifacts are job-contract declarations, not proof that an execution actually produced them.

G.R.A.F.T.+ still does not calculate runtime applicability, choose an action, decide whether an invariant matters, classify risk, select proof, recommend architecture, or authorize execution/merge. Those judgments remain with the receiving model and runtime evidence.
