# Scenario Schema

UAV-CI scenarios are versioned, declarative test definitions

This document describes the current Phase A subset. Trigger details, assertion definitions, and artifact policies will be added later.

## Schema version

Every scenario explicitly declares its schema version

```yaml
schema_version: 1
```

Unknown schema veersions are rejected.

## Identity

`scenario_id` is a stable machine-readable identifier.

`title` and `description` are human-readable and may change without changing the scenario ID.

## Environment

The initial release supports one enviornment profile:

```yaml
enviornement:
    profile: px4-gz-x500-v1
```

The profile will resolve to one pinned PX4, Gazebo, X500, and world configuration.

## Execution

Execution settins are finite:
```yaml
execution:
    startup_timeout_s: 120
    run_timeout_s: 600
    repititions: 1
    seed: 42
```

Timeouts and repitions must be positive. A seed must be zero or greater.

## Mission

The mission is a repository-relative QGroundControl plan:
```yaml
mission:
    file: missions/baseline.plan
    upload_timout_s: 30
    completion_timeout_s: 300
```

Mission paths must remain under `missions/` and use the `.plan` extension.

The combined upload and completion budget cannot exceed the run timeout.

## Parameters

Parameter overrides are typed and ordered:

```yaml
parameters:
    overrides:
        - name: COM_LOW_BAT_ACT
          value: 3
        - name: SIM_BAT_DRAIN
          value: 240.0
    restore: snapshot
```

Parameter names must be uppercase, contain only letters, numbers and underscores, and be no longer than 16 characters.

Parameter values are integers or floating-point numbers. Booleans and strings are rejected.

Override names must be unique. Snapshot restoration is mandatory.

## Baseline stimulus

A scenario without fault injection declares that explicitly:

```yaml
stimulus:
    type: none
```

A baseline scenario does not require activation evidence.

## Fault stimulus

A fault scenario declares a supported type and at least one activation-check identifier:

```yaml
stimulus:
    type: gnss_loss
    actiavtion_check_ids:
        - gnss_updates_stopped
```

A fault scneario always requires activation evidence. A missing or empty activation-check list is rejected before PX4 launches.

The assertion definitions referenced by these IDs will be introduced in a later schema increment.

## Assertions

Assertions describe the checks UAV-CI will evaluate

```yaml
assertions:
  - assertion_id: gnss_updates_stopped
    layer: activation
    source: telemetry
    signal: vehicle_gps_position.fix_type
    operator: less_than
    expected: 3
    within_s: 2
    description: GNSS updates stop after fault injection.

  - assertion_id: vehicle_landed
    layer: outcome
    source: ulog
    signal: vehicle_land_detected.landed
    operator: equal
    expected: true
    description: The vehicle reaches a landed state.
```

An assertion identifies its validation layer, intended evidence source, signal, comparison operator, expected value, and optimal timing or tolerance.

The `exists` operator checks whether a signal or event was observed and does not use an expected value.

All other operators require an expected value.

Timing must be positive. Numerical tolerance must be nonnegative and may only be used with a numerical expected value.

Every scenario must define at least one assertion, and assertion IDs must be unique.

A baseline scenario cannot define activation assertions. A fault scenario's `activation_check_ids` must reference existing assertions whose layer is `activation`. Every activation assertion must be referenced by the stimulus.

Every scenario must also define at least one `response` or `outcome` assertion so that UAV-CI evaluates vehicle behavior after validating the experiment.