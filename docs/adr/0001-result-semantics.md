# ADR 0001: Run Result Semantics

- Status: Accepted
- Date: 2026-08-28

## Context

A simulated vehicle may remain stable even when a requested fault was never activated. Treating that run a pass would create false confidence.

UAV-CI therefore needs result statuses that distinguish vehicle behavior from invalid experiements and harness failures.

## Decision

UAV-CI uses five final run states

- `pass`: The experiment was valid and all required behavior checks passed.
- `fail`: The experiment was valid, but a response or outcome check failed.
- `invalid`: A precondition or required activation check was not proven.
- `error`: The harness, evaluator, parser, or environment malfunctioned.
- `skipped`: A declared environment requirement was unsupported.

Classification uses this precedence:

1. Harness error
2. Unsupported enviornment
3. Assertion error
4. Precondition validity
5. Stimulus activation validity
6. Response and outcome evalution
7. Pass

Fault scenarios require at least one activation assertion. Baseline scenarios without an injected fault do not.

All assertions supplied during Phase A are treated as required.

## Consequences

A fault scenario cannot return `pass` or `fail` unless activation was proven.

A failed activation produces `invalid`, even if response assertions also fail.

A baseline scenario can pass without an activation assertion.

Harness and evaluator errors remain distinguished from vehicle failures.