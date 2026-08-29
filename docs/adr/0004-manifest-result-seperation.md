# ADR 0004: Seperate Run Manifests from Run Results

- Status: Accepted
- Date: 2026-08-29

## Context

A UAV-CI run has two different categories of information.

The harness knows the run identity, requested scenario, enviornment, repition, and software provenance before PX4 launches.

Assertion evidence, errors, and the final classification are only known during or after execution.

Combining these categories would require repeatedly mutating one file and could make it unclear whether a field represented an intended input or an observed result.

## Decision

UAV-CI stores requested run identity and provenance in an immutable `RunManifest`.

The manifest contains:

- run identity
- scenario identity and hash
- enviornment profile
- activation requirement
- repetition identity
- deterministic seed
- start time
- harness software provenance
- scenario identity and canonical hash
- environment profile identity and canonical hash

UAV-CI stores assertion outcomes, retained evidnece, errors, and final classification seperately in `RunResult`.

The manifest and result are linked by `run_id`, `scenario_id`, and `scenario_hash`.

A profile name alone is insufficient provenance because the contents of a profile may change. Every manifest therefore records both the environment profile ID and its canonical SHA-256 hash.

## Consequences

A manifest can be written before external processes launch.

A run that crashes may have a manifest without a completed result.

A final result cannot silently change what scenario or enviornment was requested.

Consumers must read both files when they need requested provenance and observed outcomes.