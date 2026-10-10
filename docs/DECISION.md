# Decision boundary

G.R.A.F.T.+ does not emit an architecture-decision artifact.

Earlier research versions carried derived disposition fields and a
`graph-architecture-decision.json` sidecar. Those outputs are retired from the
canonical fact-substrate pack.

The current boundary is:

- G.R.A.F.T.+ observes, identifies, relates, normalizes, and encodes;
- the receiving LLM calculates reach and blast radius;
- the receiving LLM selects proof;
- the receiving LLM classifies risk;
- the receiving LLM makes architectural and change decisions;
- merge authorization remains `not-determined`;
- execution authority is never granted by the artifact.

This separation is deliberate: observed software reality must not be contaminated
with the instrument author's architectural judgment.
