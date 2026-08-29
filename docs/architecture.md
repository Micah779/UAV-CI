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