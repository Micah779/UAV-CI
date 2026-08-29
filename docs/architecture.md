# UAV-CI Architecture

UAV-CI is organized around explicit boundaries between test definitions, runtime orchestration, external systems, and retained evidence.

## Package responsibilites

### `uav_ci.domain`

Contains immutable models and pure classification rules.

Domain code does not launch processes, connect to vehicles, or write files.

### `uav_ci.scenario`

Loads untrusted YAML, validates it through the domain models, and calculates deterministic scenario hashes.

### `uav_ci.runtime`

Owns run lifecycle concearns such as isolated directories, manifests, structured logs, process management, and cleanup.

Creating a run directory does not launch PX4 or Gazebo.

### `uav_ci.cli`

Translates user commands into calls to the scenario and runtime layers. It also converts internal errors into useful terminal output and process exit codes.

## Run directory contract

Local run output will be stored under the ignored
`artifacts/runs/` directory:

```text
artifacts/runs/<timestamp>_<scenario-id>_<run-id>/
├── inputs/
├── logs/
├── evidence/
├── reports/
├── manifest.json
└── result.json
```

The directories have these responsibilities:

- `inputs/` contains immutable snapshots of scenario and environment inputs.
- `logs/` contains harness and managed-process logs.
- `evidence/` contains telemetry captures, ULogs, and other evidence.
- `reports/` contains human-readable and machine-readable reports.
- `manifest.json` records run identity and provenance.
- `result.json` records the classified run result.

A run directory must never overwrite an existing run.

## Manifest publication

The runtime builds a manifest exclusively from a validated, fingerprinted scenario and explcit run identity.

Before publication, the writer verifies that the manifest's run ID, scenario ID, and start time match the destination run directory.

Manifest publication uses a temporary file and an atmoic hard link. An existing `manifest.json` is never overwritten. Consumers therefore observe either no manifest or one complete immutable manifest.

## Structured event log

Each run owns an append-only `logs/events.jsonl` file. Every line is one independently parseable JSON event.

Events include UTC and host-monotonic timestamps, run identity,
scenario identity, severity, component, event name, message, and typed attributes.

The UTC clock supports correlation and human investigation. The
monotonic clock supports ordering and duration measurement. Runtime logic must not calculate durations from wall-clock timestamps.

Events are never written into a run directory whose run ID or
scenario ID differs from the event.

## Managed process boundary

External programs are launched with argument tuples and without a shell. Each process receives separate append-only stdout and stderr files under the run's `logs/` directory.

Managed processes start in a new operating-system session so their process groups can be terminated together. Cleanup first sends `SIGTERM`, waits for a bounded interval, and escalates to `SIGKILL` only when necessary.

Process log files are never overwritten. Readiness detection is a separate concern and will be layered on top of this lifecycle primitive.

## Process readiness

Starting a process does not prove that the service it provides is ready. Readiness must be established separately from process
creation.

The initial readiness mechanism searches retained stdout and stderr for a declared literal marker within a bounded interval. It reports the exact stream and matching line that proved readiness.

An early process exit and a readiness timeout are distinct failures. Readiness failure does not transfer process ownership; the caller must still execute bounded cleanup.