# Scenario Schema

UAV-CI scenarios are versioned, declarative test definitions

This document describes the current Phase A subset. Mission, parameter, trigger, assertion-definition, and artifact fields will be added in later increments.

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

The profile will resolve to one pinned PX4, Gazebo, X500, and world configuration. Resolved values will be recorded in the artifact manifest.

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
