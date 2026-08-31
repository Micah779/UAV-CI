# UAV-CI
UAV-CI is a local-first flight-assurance and regression-testing
harness for PX4 software-in-the-loop simulations.

It converts manually tested PX4 and Gazebo experiments into reproducible, machine-readable scenarios with retained inputs, flight evidence, ULogs, assertions, and classified results.

UAV-CI is currently limited to one known PX4/Gazebo X500
configuration. This constraint is intentional: the initial release prioritizes reproducibility and trustworthy evidence over broad environment support.

## Project status
UAV-CI can currently execute and evaluate a complete baseline mission:

1. Validate and hash the scenario and mission.
2. Verify the pinned PX4 and Gazebo environment.
3. Create an isolated run directory.
4. Retain immutable input snapshots and a run manifest.
5. Launch PX4 SITL and Gazebo.
6. Connect to the vehicle through MAVSDK.
7. Prove vehicle preconditions before arming.
8. Upload and execute the baseline mission.
9. Prove that the vehicle became airborne.
10. Wait for landing and disarming.
11. Stop the managed simulation.
12. Capture and hash the exact PX4 ULog.
13. Analyze PX4 land-detection data with `pyulog`.
14. Publish evidence-backed assertions and `result.json`.

The working baseline assertions prove:

- vehicle preconditions passed;
- the vehicle became airborne;
- the vehicle completed a landing transition;
- the vehicle disarmed after landing.

Fault injection is the next implementation phase. Wind, GNSS loss, data-link loss, battery escalation, and unsafe-action denial are not yet complete automated scenarios.

## Core assurance rule
A fault scenario cannot pass merely because the vehicle remained stable.

UAV-CI must first prove that the intended fault reached the target subsystem. Only after activation is proven may it evaluate the vehicle response and terminal outcome.

If fault activation cannot be proven, the run is `invalid`, not `pass` or `fail`.

## Result statuses
UAV-CI uses five terminal statuses:

- `pass`: activation and required behavior were proven.
- `fail`: the test was valid, but vehicle behavior violated an assertion.
- `invalid`: required preconditions or fault activation were not proven.
- `error`: the harness could not complete or evaluate the run.
- `skipped`: the requested environment is unsupported.

## Supported environment
The initial supported profile is:

`px4-gz-x500-v1`

It pins:

- PX4 revision
  `e4a0bc726e20a6796c08786e3199771c5c914499`
- Gazebo-models revision
  `bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9`
- Gazebo Sim `8.15.0`
- PX4 target `px4_sitl`
- Gazebo target `gz_x500`
- X500 vehicle
- default Gazebo world
- MAVSDK address `udpin://0.0.0.0:14540`

The PX4 checkout and its Gazebo-models submodule must be clean and match the pinned revisions.

The environment can be changed deliberately by updating the profile, tests, and supporting documentation. UAV-CI does not silently accept a different simulator configuration.

## Development setup
UAV-CI requires Python 3.11 or newer.

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install UAV-CI and its development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the unit-test suite:

```bash
python -m pytest
```

## Validate the baseline scenario\
Validation parses the YAML, validates its typed model, resolves the mission artifact, and computes deterministic hashes without launching PX4:

```bash
uav-ci validate scenarios/baseline.yaml
```

## Verify the install simulator enviornment
Preflight compares the installed PX4 and Gazebo enviornment with the pinned profile without launching the simulator.

```bash
uav-ci preflight \
  environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

## Prepare a no-flight run
Preperation creates the run dierectory, snapshots the inputs, publishes the manifest, and records preflight evidencewithout launching or arming a vehicle:

```bash
uav-ci prepare \
  scenarios/baseline.yaml \
  --environment environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

## Run the automated baseline flight
Close QGroundControl before managed automation so UAV-CI owns the test connection and lifecycle.

Run:
```bash
uav-ci flight-check \
  scenarios/baseline.yaml \
  --environment environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

A successful run prints the classified status, retained ULog, analysis evidence, assertion outcomes, and path to `result.`.

This command controls only PX4 SITL and Gazebo. UAV-CI does not currently support real-aircraft execution.

## Run artifacts
Every run receives a unique directory beneath `artifacts/runs/`:

```text
artifacts/runs/<timestamp>_<scenario-id>_<run-id>/
├── inputs/
│   ├── scenario.json
│   ├── environment.json
│   ├── mission.plan
│   └── patches/
├── logs/
│   ├── events.jsonl
│   ├── flight.ulg
│   ├── px4_sitl.stdout.log
│   └── px4_sitl.stderr.log
├── evidence/
│   ├── preflight.json
│   ├── vehicle_preconditions.json
│   ├── mission_execution.json
│   └── land_detection.json
├── reports/
├── manifest.json
└── result.json
```

The important top-level files are:
- `manifest.json`: run identity, environment, scenario, and input provenance.
- `result.json`: final classification, assertion outcomes, and links to supporting evidence.

Run directories are non-overwriting. A new execution always receives a new run identity.

## Repository structure
```text
src/uav_ci/
├── analysis/       # ULog analysis and assurance evaluation
├── domain/         # immutable models and classification rules
├── environment/    # environment-profile loading
├── runtime/        # run lifecycle and process orchestration
├── scenario/       # scenario loading and hashing
├── vehicle/        # MAVSDK connection and mission execution
└── cli.py          # command-line interface
```

Supporting design documentation lives under docs/, including architecture decisions, evidence semantics, the scenario schema, and the known environment profile.

The activation-first rule applies to every fault implementation.
