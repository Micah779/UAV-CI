# UAV-CI

UAV-CI is a local-first flight-assurance and regression-testing harness for PX4 software-in-the-loop simulations.

It converts manually tested PX4 and Gazebo experiments into machine-readable scenarios with retained inputs, mission files, flight evidence, ULogs, assertions, and classified results.

The current implementation targets one pinned PX4/Gazebo X500 configuration. This constraint prioritizes traceability and trustworthy evidence over broad environment support.

**UAV-CI currently supports simulator execution only. Do not use it to control a physical aircraft.**

## Project status

UAV-CI has demonstrated:

- A complete automated baseline mission.
- Vehicle precondition checks before arming.
- Mission upload, cursor reset, and execution.
- Observed takeoff, mission completion, landing, and disarming.
- Managed PX4/Gazebo startup and shutdown.
- Capture and hashing of the PX4-announced ULog.
- Evidence-backed baseline classification.
- Run-owned X500 model preparation for wind.
- Wind publication after the vehicle is observed airborne.
- Bounded wind observation and activation assessment.
- INVALID classification when wind activation cannot be proven.
- A successful end-to-end wind run using a separate ten-second activation-window scenario.

### Recorded wind results

The following results were inspected on September 3, 2026:

| Scenario | Activation window | Recorded outcome |
|---|---:|---|
| `scenarios/wind.yaml` | 5 seconds | INVALID: insufficient qualifying observations before the deadline |
| `scenarios/wind_10s.yaml` | 10 seconds | PASS: activation and the landing outcome were proven |

The successful ten-second run retained two consecutive qualifying observations at approximately 4.46 and 5.20 seconds after command publication began.

The ten-second result does not satisfy the original five-second requirement. The original scenario and its INVALID evidence remain unchanged.

One successful wind run is an initial demonstration, not a repeatability or reliability claim.

### Remaining work

The broader regression platform is not complete. Remaining work includes:

- Repeatability checks for the demonstrated wind scenario.
- Additional vehicle-response assertions.
- GNSS-loss, data-link-loss, battery-escalation, and unsafe-action-denial scenarios.
- Human-readable reporting and regression summaries.
- Batch execution and automated CI integration.
- Validation beyond the pinned local environment.

## Core assurance rule

A fault scenario cannot pass merely because the vehicle remained stable or completed its mission.

UAV-CI must first prove the configured activation condition. Only after that condition is proven may it classify the vehicle response and terminal outcome.

If required preconditions or fault activation cannot be proven, the run is `invalid`, not a vehicle-behavior `pass` or `fail`.

For wind, the implemented activation condition is a bounded transition in the observed Gazebo wind field under the pinned environment contract. It is not a direct measurement of aerodynamic force on the vehicle.

## Result statuses

UAV-CI models five terminal statuses:

- `pass`: required preconditions, any required activation, and the evaluated behavior assertions passed.
- `fail`: the experiment was valid, but an evaluated behavior assertion failed.
- `invalid`: required preconditions or fault activation were not proven.
- `error`: an execution, infrastructure, or evidence-processing problem prevented normal evaluation.
- `skipped`: an unsupported-environment condition was explicitly classified as skipped.

Baseline scenarios do not require fault activation.

A declared status is not a promise that every command automatically produces that status for every corresponding condition. For example, failed environment preflight in `flight-check` is classified as INVALID.

The current runtime conservatively treats mission-execution exceptions as errors. It does not automatically interpret every aborted mission as a vehicle-behavior failure.

## Supported environment

The implemented profile is `px4-gz-x500-v1`.

It declares:

| Setting | Value |
|---|---|
| PX4 revision | `e4a0bc726e20a6796c08786e3199771c5c914499` |
| Gazebo-models revision | `bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9` |
| Gazebo Sim | `8.15.0` |
| PX4 target | `px4_sitl` |
| Simulator target | `gz_x500` |
| Vehicle | X500 |
| World | `default` |
| MAVSDK address | `udpin://0.0.0.0:14540` |

The PX4 checkout and its Gazebo-models submodule must match the declared revisions and pass clean-worktree checks.

The demonstrated host is macOS. Broader operating-system and environment compatibility has not been established.

See [the environment profile documentation](docs/environment-profile.md) for host prerequisites, Python environment handling, and wind-model preparation.

## Development setup

The package declares Python 3.11 or newer. The recorded local development runs used Python 3.14.7; a broader Python compatibility matrix has not been demonstrated.

From the UAV-CI repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the software tests:

```bash
python -m pytest
```

These tests do not replace live PX4/Gazebo validation.

Installing UAV-CI does not install the complete PX4/Gazebo build environment. The pinned PX4 checkout, simulator, build tools, and PX4-side Python environment must already be configured.

## Validate a scenario

Validation parses the YAML, validates its typed model, resolves the referenced mission, and calculates scenario and mission hashes without launching PX4.

```bash
uav-ci validate scenarios/baseline.yaml
uav-ci validate scenarios/wind.yaml
uav-ci validate scenarios/wind_10s.yaml
```

The mission hash identifies the mission file separately from the scenario hash.

## Verify the installed environment

Preflight compares the installed environment with the declared profile without launching PX4 or Gazebo.

The examples assume that `PX4-Autopilot` is a sibling of the UAV-CI repository.

```bash
uav-ci preflight \
  environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

Do not proceed to a managed flight when preflight fails.

## Prepare a no-flight run

Preparation creates a unique run directory, retains input snapshots, publishes a manifest, and records environment-preflight evidence.

It does not launch the simulator or arm the vehicle.

```bash
uav-ci prepare \
  scenarios/baseline.yaml \
  --environment environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

## Managed-flight operating procedure

For the demonstrated local setup:

1. Disconnect physical vehicles.
2. Stop any previous PX4/Gazebo session.
3. Open QGroundControl as used in the verified local runs.
4. Do not start PX4 separately with `make`.
5. Let UAV-CI launch and stop its own simulator session.
6. Do not manually command the vehicle or change simulator wind during the test.

QGroundControl is not launched or managed by UAV-CI. The verified setup used it open; unattended operation without QGroundControl has not been established.

The environment is intended for one managed simulator session at a time. Concurrent sessions can interfere through shared ports, Gazebo transport, and PX4 build/runtime paths.

### Baseline flight

```bash
uav-ci flight-check \
  scenarios/baseline.yaml \
  --environment environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

The baseline evaluation covers vehicle readiness, observed takeoff, landing, and disarming.

### Ten-second wind diagnostic

```bash
uav-ci flight-check \
  scenarios/wind_10s.yaml \
  --environment environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

This scenario requests 5 m/s wind toward world +Y after takeoff. It allows ten seconds to obtain the required activation evidence.

The wind evaluation produces assertions for:

- `vehicle_ready`
- `wind_reached_vehicle`
- `vehicle_landed`

The wind scenario currently evaluates activation and landing. It does not evaluate path-tracking accuracy, maximum attitude excursion, sustained exposure, or directly measured aerodynamic force.

A successful command prints the classified result, mission observations, activation status when applicable, retained ULog information, assertion outcomes, and `result.json` path.

Preserve failed and invalid runs. Do not edit retained inputs or results to change their classification.

## Wind activation evidence

A successful publication command alone does not prove activation.

The implemented evaluator requires:

- A fresh, calm pre-command baseline.
- Wind enabled on the target link.
- Stable world, wind, model, and link entity identities.
- Advancing simulation time and iteration count.
- An unpaused simulator.
- A requested seed consistent with the command.
- Two consecutive observations meeting the speed, direction, and vertical-wind criteria.
- Observation completion within the scenario's activation window.

The activation window begins when command publication starts, not when publication finishes.

For the current scenarios, observed horizontal speed must reach at least 4.5 m/s. Additional evaluator tolerances are documented in [wind activation assessment](docs/wind-activation.md).

Only the first qualifying pair is used to prove activation. Continued exposure throughout the mission is not independently monitored.

Cleanup attempts to publish zero wind with wind disabled. A successful cleanup receipt is not proof of restored simulator state; the owning runtime also stops the simulator session.

## Run artifacts

Runs are stored beneath the ignored `artifacts/runs/` directory.

A successful wind run can contain:

```text
artifacts/runs/<timestamp>_<scenario-id>_<run-id>/
├── inputs/
│   ├── scenario.json
│   ├── environment.json
│   ├── mission.plan
│   └── patches/
├── workspace/
│   └── models/
│       └── x500_base/
├── logs/
│   ├── events.jsonl
│   ├── flight.ulg
│   ├── px4_sitl.stdout.log
│   └── px4_sitl.stderr.log
├── evidence/
│   ├── preflight.json
│   ├── vehicle_preconditions.json
│   ├── mission_execution.json
│   ├── land_detection.json
│   └── wind/
│       ├── baseline/
│       │   └── sample-000001.json
│       ├── activation/
│       │   └── sample-*.json
│       ├── command.json
│       ├── activation.json
│       └── cleanup-command.json
├── reports/
├── manifest.json
└── result.json
```

Artifacts depend on how far execution progressed. Failed or invalid runs may not contain every file shown above.

- `manifest.json` records run identity and declared input provenance.
- `result.json` records the final classification, assertions, and evidence references.
- `logs/flight.ulg` contains the captured PX4 flight log.
- `evidence/wind/activation.json` records the activation decision and links to its observations.
- `reports/` is reserved for future reporting functionality.

Each execution receives a new run identity. Exclusive publication prevents normal writers from overwriting existing snapshots and results.

These local files are not a cryptographically tamper-proof archive. Retain and protect them when using results as project evidence.

## Repository structure

```text
src/uav_ci/
├── analysis/       # ULog analysis and assurance evaluation
├── domain/         # Typed models and classification rules
├── environment/    # Environment-profile loading
├── faults/         # Wind commands, observations, and activation
├── runtime/        # Run lifecycle, artifacts, and process ownership
├── scenario/       # Scenario loading and hashing
├── vehicle/        # MAVSDK connection and mission execution
├── clocks.py       # Shared clock utilities
└── cli.py          # Command-line interface
```

## Documentation

- [Architecture](docs/architecture.md)
- [Environment profile](docs/environment-profile.md)
- [Scenario schema](docs/scenario-schema.md)
- [Evidence model](docs/evidence-model.md)
- [Wind command adapter](docs/wind-command-adapter.md)
- [Wind observer](docs/wind-observer.md)
- [Wind activation assessment](docs/wind-activation.md)
- [Wind controller](docs/wind-controller.md)

Architecture decisions are retained under `docs/adr/`.

UAV-CI is a working early assurance harness, not a completed multi-fault regression platform or an aircraft safety certification.