# ADR 0003: Canonical Scenario Hashing

- Status: Accepted
- Date: 2026-08-29

## Context

UAV-CI must retain the exact identity of the scenario used for every run. Hashing raw YAML bytes would treat comments, whitespaces, and mapping-key order as changes to the experiment.

A scenario hash should change when the validated meaning of the scenario changes, not when its presentation changes.

## Decision

UAV-CI parses scenario files with PyYAML's safe loader and validates the resulting data with `ScenarioSpec`.

The validated model is serialized as canonical JSON with:

- JSON compatible model values
- all validated defaults included
- mapping keys sorted
- compact seperators
- UTF-8 encoding
- non-finite floating-point values prohibited

UAV-CI calculates a SHA-256 digest from those canonical JSON bytes.

The source file path is not included in the hash.

List ordering remains significant.

## Consequences

Comments, whitespace, and mapping-key order do not affect scenario identity.

Moving an unchanged scenario file does not affect its identity.

Explicit default values and automatically supplied default values produce the same hash.

Changes to validated scenario values, assertion ordering, or schema semantics may change the hash.

Invalid scenarios are rejected before a hash is produced.