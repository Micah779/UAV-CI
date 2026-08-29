# UAV_CI

UAV-CI is a local-first flight assurance and regression-testing harness for PX4 software-in-the-loop simulations (SITL).

If you have ever tried to reproduce flight tests across PX4 SITL, Gazebo, and QGroundControl manually; you understand the pain.

It will convert manually tested PX4 and Gazebo experiments into reproducible, machine-readable scenarios with explicit activation evidence, response assertions, and retained flight artifacts.

# Project status

The current implementation provides:

- shared typed domain vocabulary
- immutable scenario and result models
- activation-first result classification
- safe YAML scenario loading
- deterministic scenario hashing
- a schema-validation CLI
- unit-test coverage for the foundation

It does not yet launch PX4 or Gazebo

# Core testing rule

A fault scenario cannot pass merely because the vehicle remained stable.

UAV-CI must first prove that the intended fault reached the target subsystem. Only then may it evaluate the flight stack response and terminal outcome.

# Development setup

UAV-CI requires Python 3.11 or newer

Create a virtual enviornment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project and its dev dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
python -m pytest
```

Validate a scenarioi without launching PX4

```bash
uav-ci validate scenarios/baseline.yaml
```