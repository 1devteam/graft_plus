# G.R.A.F.T.+ deployment synchronization contract

## Purpose

Keep canonical G.R.A.F.T.+ semantic evolution independent from the deployed public website without introducing a runtime service dependency.

## Authorities

- **Semantic authority:** `1devteam/graft_plus`.
- **Website execution authority:** `1devteam/1devteam-web` at `/graft`.
- **Synchronization transport:** GitHub commits, branches, pull requests, review, and CI.
- **Runtime transport:** none. The public website must not require a tunnel, Cloudflare Worker, localhost process, or external G.R.A.F.T.+ API in order to reconstruct a public repository.

## Promotion rule

A change in `graft_plus` does not automatically become website behavior. Approved semantics are ported into the browser implementation in `1devteam-web`, tested there, and merged there. The website remains self-contained after the port.

Every website artifact must expose enough provenance to answer:

1. Which embedded engine produced this pack?
2. Which embedded graph schema did it use?
3. Which repository is the semantic authority?
4. Which repository owns deployed execution?
5. Which canonical revision was used as the synchronization reference?
6. Is parity with that canonical revision verified, or is the browser implementation behind?

A canonical reference SHA is a synchronization checkpoint only. It must never be interpreted as proof of parity unless the port's compatibility tests establish parity for the declared semantic surface.

## GitHub synchronization workflow

1. Develop and validate reconstruction semantics in `1devteam/graft_plus`.
2. Select a canonical commit SHA as the synchronization source.
3. Open a dedicated `1devteam-web` branch/PR that ports the applicable behavior into the embedded browser engine.
4. Record the source SHA, canonical schema, embedded schema, synchronization mode, and parity status in website provenance metadata.
5. Run browser-side reconstruction tests and representative repository fixtures.
6. Review the semantic delta. Merge only after the website remains self-contained and the declared provenance is accurate.
7. If the browser port intentionally trails canonical semantics, emit `behind-canonical` rather than claiming parity.

## Non-goals

This contract does not require or authorize automatic production updates, a canonical backend service, Cloudflare graph execution, merge authority, or replacement of the website's browser execution model.
