# Known Environment Profile

UAV-CI currently implements one known execution profile:

`px4-gz-x500-v1`

The profile declares the simulator configuration against which scenarios are validated and run. It is not a general compatibility declaration for arbitrary PX4 revisions, Gazebo versions, vehicles, or host systems.

## Pinned configuration

| Setting | Declared value |
|---|---|
| PX4 repository | `PX4-Autopilot` |
| PX4 commit | `e4a0bc726e20a6796c08786e3199771c5c914499` |
| PX4 description | `v1.18.0-beta1-416-ge4a0bc726e` |
| Gazebo-models commit | `bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9` |
| Gazebo Sim | `8.15.0` |
| PX4 build target | `px4_sitl` |
| Simulator target | `gz_x500` |
| Gazebo world | `default` |
| Vehicle model | `x500` |
| MAVSDK address | `udpin://0.0.0.0:14540` |

The profile file is `environments/px4-gz-x500-v1.yaml`.

The PX4 checkout and the `Tools/simulation/gz` submodule must match the declared revisions and pass clean-worktree checks.

A commit hash alone does not identify an environment when local source modifications are present.

## Demonstrated host setup

The recorded local runs used macOS with Python 3.14.7 for UAV-CI.

The package declares Python 3.11 or newer, but this is not evidence that every supported Python version or operating system has been validated with the complete simulator stack.

The host must already provide:

- The pinned PX4 checkout and its required dependencies.
- The pinned Gazebo-models submodule.
- Gazebo Sim.
- Git and Make.
- A working PX4-side Python environment.
- The UAV-CI Python environment and dependencies.

Installing UAV-CI does not install or configure the complete simulator toolchain.

### Separate Python environments

UAV-CI runs from its own virtual environment.

The managed PX4 launch uses the Python environment under:

```text
PX4-Autopilot/.venv/
```

Preflight checks for:

```text
PX4-Autopilot/.venv/bin/python
```

It also checks that this interpreter can import `kconfiglib` and `menuconfig`.

These checks catch the previously encountered PX4 configuration failure caused by an unavailable `menuconfig` module. They are not a complete audit of every PX4 build dependency.

### QGroundControl and session ownership

The verified local operating procedure used QGroundControl open.

QGroundControl is not started, stopped, or managed by UAV-CI. Unattended operation without it has not been established.

During managed tests:

- Keep physical vehicles disconnected.
- Stop previously launched PX4/Gazebo sessions.
- Do not launch a separate simulator with `make`.
- Do not manually arm, upload missions, change modes, or change wind during the test.
- Allow UAV-CI to own the simulator lifecycle and mission commands.

Only one managed simulator session is supported at a time. Shared ports, Gazebo transport names, and PX4 build/runtime paths make concurrent execution unsafe for evidence attribution.

The configured UDP endpoint is not an independent physical-aircraft safety interlock.

## Profile validation and identity

Environment YAML is parsed with PyYAML's safe loader and validated through the immutable `EnvironmentProfile` model.

Declared patch files must resolve beneath the UAV-CI repository and match their declared SHA-256 digests.

A missing patch or digest mismatch makes profile loading fail.

The validated profile is serialized as canonical JSON and assigned a SHA-256 environment hash. YAML comments, whitespace, and mapping-key order do not affect that identity.

The environment hash identifies the declared configuration. It does not prove that the installed host matches it.

Runtime preflight performs that separate comparison.

## Runtime preflight

Preflight is read-only and does not launch PX4 or Gazebo.

It checks:

- PX4 repository existence.
- PX4 revision.
- PX4 clean-worktree state.
- PX4-side Python interpreter availability.
- Imports of `kconfiglib` and `menuconfig`.
- Gazebo-models directory existence.
- Gazebo-models revision.
- Gazebo-models clean-worktree state.
- Gazebo version.
- Make availability.

Run preflight from the UAV-CI repository:

```bash
uav-ci preflight \
  environments/px4-gz-x500-v1.yaml \
  --px4-repository ../PX4-Autopilot
```

A failed environment precondition is not a vehicle-behavior failure.

For `flight-check`, failed environment preflight produces an INVALID result when that result can be published.

Passing preflight does not establish simulator readiness, MAVSDK connectivity, vehicle readiness, or flight success. Those are separate runtime checks.

## Run-owned wind capability

The wind implementation requires wind effects to be enabled on the X500 base link:

```xml
<enable_wind>true</enable_wind>
```

The repository retains the required modification as:

```text
environments/patches/x500-enable-wind.patch
```

The profile declares its SHA-256 digest:

```text
ec27587df8f351b8ea3166c4d8d49c12ffabbd676ecc4cfbde52a1b1e0c71712
```

For wind scenarios, UAV-CI:

1. Validates the declared patch and retains a run input snapshot.
2. Copies the required `x500_base` model into the run workspace.
3. Checks and applies the patch to that run-owned model.
4. Verifies the expected wind-enable modification.
5. Places the run-owned model resources first in the managed Gazebo resource search path.

The resulting model is stored beneath:

```text
workspace/models/x500_base/
```

The wind patch is not applied directly to the shared PX4 source checkout.

This isolation applies to the modified model resources. PX4 builds and runtime logs still use the supplied PX4 checkout's build/runtime paths; the entire simulator installation is not copied into each run.

## Wind transport and observations

The initial implementation targets:

- World: `default`
- Model entity: `x500_0`
- Link: `base_link`
- Wind publication topic: `/world/default/wind`
- Full-state service: `/world/default/state`

Direction is expressed in the Gazebo world frame, measured from positive X toward positive Y. A request of 90 degrees therefore points toward world +Y.

The decoder reads actual wind from the Wind entity's `WorldLinearVelocity` component. It retains `WorldLinearVelocitySeed` separately as the requested seed.

A command receipt or matching seed alone is not activation proof.

The decoder uses the repository-bundled `gazebo_state.desc` descriptor set. The associated upstream license is retained in `src/uav_ci/faults/data/gz-msgs-LICENSE`.

## Activation timing

The activation budget begins at wind publication start. Publication latency and subsequent state-request latency consume that budget.

The original scenario uses five seconds:

```text
scenarios/wind.yaml
```

The diagnostic variant uses ten seconds:

```text
scenarios/wind_10s.yaml
```

Changing the activation window changes the scenario requirement and scenario identity. It does not modify or retroactively reclassify earlier runs.

Both scenarios retain the same requested speed, direction, minimum proven speed, and two-consecutive-observation policy.

## Recorded verification

On September 3, 2026:

- The five-second scenario returned INVALID because sufficient qualifying observations were not obtained before its deadline.
- The ten-second variant returned PASS.
- Its qualifying samples completed approximately 4.46 and 5.20 seconds after publication began.
- Mission telemetry recorded takeoff, completion, landing, and disarming.
- PX4 ULog analysis independently supported the airborne-to-landed transition.

These observations demonstrate the ten-second variant on the known local setup. They do not establish the original five-second requirement or broader repeatability.

## Cleanup and limits

After wind publication is attempted, the controller attempts a bounded disable command requesting zero wind and `enable_wind: false`.

A successful cleanup receipt is not proof of restored simulator state. Cleanup records retain `restoration_proven: false`.

The owning runtime also stops its managed simulator session.

The current wind evidence establishes a bounded calm-to-wind simulator-field transition under the pinned configuration. It does not directly prove:

- Aerodynamic force applied to the vehicle.
- Sustained wind exposure throughout the mission.
- Path-tracking or attitude performance.
- Physical-aircraft behavior.
- Compatibility with arbitrary worlds or multiple simulator sessions.

## Deliberate environment changes

Do not bypass revision, cleanliness, patch-integrity, or activation checks to make a run pass.

A deliberate environment change should include:

1. Updated profile declarations.
2. Any required patch and digest updates.
3. Relevant software-test updates.
4. Fresh environment preflight.
5. Fresh simulator validation.
6. Documentation of the new evidence and limitations.

Retain earlier manifests and results under their original identities.