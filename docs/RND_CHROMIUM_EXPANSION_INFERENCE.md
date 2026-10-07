# G.R.A.F.T.+ R&D — Chromium-scale reconstruction and expansion inference

Date: 2026-10-06  
Canonical checkpoint: `19a0e493be850740eb8d3307a8c3b0686f35eda4`  
Canonical graph schema: `1.7`

## Purpose

This note records the current G.R.A.F.T.+ research direction exposed by the Chromium-scale browser experiment. It is deliberately an R&D record, not an implementation plan or product requirement.

The experiment is intended to measure whether a machine-readable architectural substrate can reduce repository rediscovery work for an LLM while preserving explicit uncertainty, provenance, and authority boundaries.

## Current architectural invariant

- `1devteam/graft_plus` is the semantic authority for canonical G.R.A.F.T.+ reconstruction behavior.
- `1devteam/1devteam-web` is the execution authority for the deployed browser workbench.
- Approved semantics move through GitHub-reviewed ports.
- The public workbench remains self-contained. Cloudflare may host the site but does not execute or supervise the graph.
- Artifact provenance must identify the producing engine/schema and must not claim parity with canonical G.R.A.F.T.+ unless parity is actually verified.

## Chromium experiment design

Preserve the same Chromium subject revision across comparison runs.

The intended progression is:

1. **Old browser graph artifact** — historical baseline already captured.
2. **Canonical schema 1.7 browser port** — measure the value of the current canonical graph independently.
3. **Schema 1.7 plus expansion-affordance representation** — measure the incremental value of architectural optionality/expansion inference.

Do not combine steps 2 and 3 before taking the schema 1.7 baseline. Keeping those variables separate makes the result interpretable.

For each run, retain:

- subject SHA;
- producing engine and graph schema;
- canonical reference SHA;
- node and edge totals;
- edge counts by type;
- inventory and relationship-parsed file counts;
- unresolved references by class;
- relationship-boundary counts;
- build definitions and build-input edges;
- subsystem and cross-language subsystem counts;
- governance boundaries;
- evidence precision counts;
- completeness residuals;
- artifact production timing;
- browser responsiveness observations;
- any files/items discovered but not ingested.

## Large-repository browser finding

A Chromium run reached approximately 29.5k discovered/ingested items in the browser. The UI rounded near-complete ingestion to 100% while a small residual count remained.

This exposes two separate concerns:

### Exact progress accounting

Progress should preserve exact numerator/denominator values. A display may round for presentation, but the artifact/run record should retain exact discovered, ingested, skipped, failed, and unresolved counts.

A rounded `100%` must never imply that every discovered item was successfully ingested.

### Materialization scheduling

After ingestion, Chromium-scale reconstruction can keep the browser main thread busy long enough for the browser to report that the page is not responding.

The observed behavior is consistent with main-thread starvation during graph construction, relationship resolution, completeness analysis, serialization, and artifact packaging rather than proof of a crashed reconstruction.

This is an execution-scheduling limitation of the browser implementation, not evidence that the graph should move to a backend service.

A future browser implementation should evaluate a Web Worker boundary:

```text
UI thread
  -> repository ingestion / progress
  -> Web Worker
       -> graph reconstruction
       -> semantic extraction
       -> evidence/completeness
       -> serialization
       -> artifact packaging
  -> completed artifact / staged progress
```

The browser execution authority remains unchanged and no Cloudflare Worker, tunnel, or remote graph runtime is implied.

Candidate user-visible stages include:

- INGEST
- RELATIONSHIPS
- SEMANTICS
- BUILD TOPOLOGY
- EVIDENCE
- COMPLETENESS
- SERIALIZATION
- PACKAGING

Operator timing marker for the current run: **10:10**, user-provided local-clock marker for the point at which ingest had effectively completed and artifact materialization was underway. Treat this as an approximate operational marker, not a machine timestamp.

## Expansion inference

G.R.A.F.T.+ should make architectural expansion *inferable* without becoming a planner.

The artifact should not emit recommendations such as “add provider X” or “build feature Y.”

Instead it should expose the structural facts from which an LLM can infer architectural optionality.

Candidate factual surfaces include:

- interfaces, protocols, abstract types, and traits;
- registries and dispatch tables;
- plugin and provider boundaries;
- factories and adapter families;
- event producers and consumers;
- configuration-selected implementations;
- capability declarations;
- sibling implementations and repeated architectural motifs;
- contracts with low implementation cardinality;
- unconsumed or lightly consumed outputs;
- unresolved relationship boundaries;
- subsystem interfaces;
- build-time feature flags;
- optional dependencies;
- declared but unused configuration keys;
- entrypoints and exposed APIs;
- data-model extension points;
- cross-language boundaries;
- generated/authored/vendored boundaries;
- ownership and governance boundaries;
- test matrices and missing combinations.

These are facts or measurable structural properties. They do not themselves assert that an expansion is desirable.

## Epistemic separation for expansion questions

When a receiving model is asked what a repository could expand into, it should preserve three layers:

1. **Proven** — directly represented in the artifact.
2. **Inferred** — architectural affordance deduced from graph structure and evidence.
3. **Proposed** — a possible product/engineering expansion suggested by the model or user.

Example:

- Proven: a provider registry contains two concrete implementations and tests generic provider behavior.
- Inferred: the architecture appears capable of accepting additional provider implementations.
- Proposed: add a specific third provider.

Only the first belongs in canonical G.R.A.F.T.+ facts. The second is LLM reasoning over the artifact. The third is planning.

## Architectural optionality research

A future research dimension is **architectural optionality**: measurable structural freedom present in a repository without assigning subjective feature recommendations.

Potential measurements include:

- extension-point count;
- implementation cardinality per contract;
- registry/provider cardinality;
- producer/consumer asymmetry;
- unconsumed output count;
- optional dependency count;
- configurable boundary count;
- sibling-pattern completeness;
- cross-subsystem connectivity;
- unresolved-but-declared extension boundaries;
- test-matrix coverage across interchangeable implementations.

These metrics should remain descriptive. They are useful because they can compress the amount of source an LLM must inspect before identifying plausible expansion paths.

## Machine-native representation research

The broader hypothesis remains that substantial LLM work in software engineering is spent reconstructing deterministic structure from human-oriented serializations.

Relevant concepts under active R&D:

- **serialization tax** — compute spent recovering structure from source/text representation;
- **representation leakage** — leaving the graph to inspect source merely to discover a structural fact that should have been represented;
- **missing machine state** — a deterministic answer still requiring inference/query because the artifact omitted it;
- **inference displacement** — reasoning eliminated because the artifact directly represents the needed structure;
- **semantic compute efficiency** — useful reasoning performed per unit of model/context compute;
- **reasoning-path compression** — shortening the sequence of searches, file reads, and deductions required to answer architectural questions.

The graph should be judged not only by inventory size, but by whether it lets a receiving model answer architectural questions with less rediscovery and less representation leakage.

## Chromium evaluation questions

The Chromium artifact should be evaluated for more than raw scale.

Questions include:

- Are C/C++ and GN/Ninja-relevant source/build relationships represented?
- Are generated and vendored regions distinguished from authored source?
- Are subsystem hierarchies useful enough to reduce source navigation?
- Are cross-language relationships represented without inventing dependencies?
- Are governance surfaces such as OWNERS/PRESUBMIT/SECURITY visible?
- Are unresolved build/runtime relationships captured as explicit boundaries?
- Are evidence anchors precise enough to support verification?
- Are tests connected to the components they prove?
- Are canonical node identities stable and duplicate-free?
- Does the artifact preserve exact ingestion/completeness residuals?
- Can an LLM infer credible expansion affordances from the artifact without rereading the repository?
- What source inspections does the LLM still need, and why?

## Decision discipline

Do not use the Chromium run as proof merely because it produces a large artifact.

A successful experiment requires distinguishing:

- ingestion scale;
- structural coverage;
- relationship fidelity;
- evidence precision;
- completeness honesty;
- browser execution scalability;
- inference displacement;
- expansion inferability.

The next implementation decision should be based on the resulting artifact and comparison evidence, not on artifact size alone.
