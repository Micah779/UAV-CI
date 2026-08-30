# ADR 0005: Mission artifact identity

## Status

Accepted

## Context

A scenario references a QGroundControl mission file by path. The
scenario YAML hash alone does not identify the mission contents, and the referenced file could be missing or change after validation.

## Decision

Scenario loading validates the referenced QGroundControl plan and calculates a SHA-256 digest over its exact bytes.

The run manifest records the declared mission path and mission hash. Preparation copies the already-validated bytes into the run input directory. Execution uses only that immutable snapshot.

The canonical scenario hash remains the identity of validated YAML semantics. Mission bytes have a separate identity because formatting changes to the QGroundControl JSON change the exact executed input.

## Consequences

A missing or invalid mission prevents preparation.

Changing mission contents changes the mission hash even when the
scenario YAML is unchanged.

Run artifacts contain enough information to prove which mission was executed.