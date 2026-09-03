# UAV-CI Architecture

UAV-CI separates scenario definitions, environment validation, simulator ownership, vehicle commands, fault activation, evidence processing, and result classification.

Its central design rule is:

> A fault experiment must establish its configured activation condition before vehicle-response results can be classified as PASS or FAIL.

The current implementation supports baseline missions and a constrained wind scenario in one pinned PX4/Gazebo X500 environment.

## Package responsibilities

### `uav_ci.domain`

Contains typed models for scenarios, environments, manifests, evidence references, assertion results, and run results.

It also contains the classification rules that derive final status from preconditions, activation, behavior assertions, and explicit error conditions.

Domain code does not launch processes, connect to vehicles, or publish run artifacts.

### `uav_ci.scenario`

Loads scenario YAML, validates the model, resolves the referenced mission artifact, and calculates scenario and mission hashes.

The scenario hash identifies validated scenario semantics. The separate mission hash identifies the referenced mission file's bytes.

### `uav_ci.environment`

Loads environment profiles, validates declared patch files and digests, and calculates environment identity.

Profile loading establishes internal consistency. It does not establish that the installed simulator matches the profile.

### `uav_ci.runtime`

Coordinates run preparation and execution.

Responsibilities include:

- Unique run directories.
- Input snapshots and manifests.
- Environment preflight.
- Structured event logging.
- Managed simulator processes and readiness.
- Vehicle and fault lifecycle orchestration.
- ULog capture.
- Result publication.
- Best-effort retention of error and INVALID evidence.

Creating a run directory or preparing a run does not itself launch PX4 or arm a vehicle.

### `uav_ci.vehicle`

Wraps MAVSDK operations for connection, precondition observation, and mission execution.

Mission execution includes mission upload, resetting the current mission item, arming, starting the mission, observing airborne state, monitoring completion, and confirming landing and disarming.

The optional airborne callback allows runtime orchestration to activate wind after takeoff has been observed.

The mission executor also checks that the vehicle is still airborne after the callback returns.

### `uav_ci.faults`

Contains the fault lifecycle contract and the implemented wind components:

- Run-owned model preparation.
- Wind command publication.
- Gazebo diagnostic screening.
- Full-state decoding.
- Bounded observation and artifact retention.
- Pure activation assessment.
- Managed activation and cleanup.

The wind controller does not own PX4 startup, vehicle arming, or final run classification.

### `uav_ci.analysis`

Analyzes retained flight evidence and builds assurance results.

The implemented analysis includes:

- PX4 ULog land-detection analysis.
- Baseline assertion evaluation.
- Constrained wind assertion evaluation.

Wind evaluation requires a proven activation result before producing behavior assertions.

### `uav_ci.cli`

Parses user commands, invokes the appropriate loading or runtime operations, and displays results and artifact locations.

For completed `flight-check` results, PASS returns exit code zero. Non-PASS results and handled command failures return a nonzero exit code.

### `uav_ci.clocks`

Provides shared clock utilities.

Clock domains are retained explicitly rather than treated as interchangeable timestamps.

## Execution lifecycle

A successful managed flight follows this sequence:

1. Load and validate the scenario, mission, and environment.
2. Allocate a unique run identity and directory.
3. Retain input snapshots and publish the manifest.
4. Perform environment preflight.
5. Prepare run-owned wind model resources when required.
6. Launch PX4 SITL and Gazebo.
7. Establish process readiness.
8. Establish MAVSDK connectivity.
9. Observe vehicle preconditions.
10. Upload and execute the snapshotted mission.
11. Observe airborne state.
12. For wind, request and assess activation through the airborne callback.
13. Complete the mission and observe landing and disarming.
14. Attempt wind cleanup when applicable.
15. Stop the owned simulator session.
16. Capture the PX4-announced ULog.
17. Enforce the activation gate.
18. Analyze retained flight evidence.
19. Build and publish the classified result.

Error paths can interrupt this sequence. Available artifacts reflect the stages actually reached.

## Activation-first classification

Wind activation assessment occurs while the mission is running.

If activation remains unproven without an infrastructure exception, the current orchestration allows bounded mission completion and cleanup. It then publishes INVALID without evaluating vehicle-response assertions.

The activation gate is applied after cleanup and ULog capture. A cleanup or capture error on an otherwise successful path must not be hidden by an INVALID activation result.

The wind result currently contains:

- `vehicle_ready`: precondition.
- `wind_reached_vehicle`: activation.
- `vehicle_landed`: outcome.

A passed activation assertion does not imply that all possible vehicle behaviors were acceptable. Only the implemented outcome assertions are evaluated.

## Wind evidence boundaries

The wind command adapter retains command arguments, timing, output, receipts, and errors.

The observer retains raw Gazebo state responses and decoded observations.

The activation evaluator checks a fresh calm baseline and two consecutive qualifying post-command observations.

The controller publishes an activation assessment linking:

- The stimulus.
- The command record.
- The baseline observation.
- Collected observations.
- Supporting observations.
- The activation decision and reason.

The resulting `EvidenceRef` identifies a harness assessment in the host-monotonic clock domain.

Gazebo simulation timestamps remain in the linked observation records. They are not relabeled as UTC or PX4 boot time.

The evaluator itself does not read artifact files or verify their hashes. Its caller is responsible for supplying records from the same managed simulator session.

## Run directory contract

Local run output is stored under the ignored `artifacts/runs/` directory:

```text
artifacts/runs/<timestamp>_<scenario-id>_<run-id>/
├── inputs/
├── workspace/
├── logs/
├── evidence/
├── reports/
├── manifest.json
└── result.json
```

Directory responsibilities:

- `inputs/`: retained scenario, environment, mission, and patch snapshots.
- `workspace/`: run-owned mutable execution resources, including patched wind models.
- `logs/`: structured events, managed-process output, and the captured PX4 ULog.
- `evidence/`: preflight, telemetry, analysis summaries, and wind observations and assessments.
- `reports/`: reserved for future reporting functionality.
- `manifest.json`: run identity and declared provenance.
- `result.json`: final classification and assertion evidence references.

A new execution receives a new run identity. Existing result and snapshot paths are not reused for a later execution.

The artifact layout is not a promise that every run produces every artifact. For example, an early preflight rejection has no flight ULog.

## Manifest and result publication

The manifest binds the run to:

- Run ID and start time.
- Scenario ID and hash.
- Mission path and hash.
- Environment profile and hash.
- Activation requirement.
- Repetition and seed metadata.
- Harness package version, Python version, and platform.

The current harness provenance does not include the UAV-CI Git commit. Package version alone is not a complete source revision identifier.

Before publishing a manifest, the writer checks its run ID, scenario ID, and start time against the destination run directory.

Before publishing a result, the writer checks its identity, scenario hash, activation requirement, and start time against the manifest.

Exclusive publication uses temporary files and an atomic hard-link operation. Normal writers cannot overwrite an existing manifest or result, and readers do not observe a partially written final artifact.

This provides write-once publication behavior, not tamper-proof storage against later external modification.

## Structured event log

Each run owns an append-only `logs/events.jsonl` file.

Events contain:

- Schema version.
- UTC timestamp.
- Host-monotonic timestamp.
- Run and scenario identity.
- Severity.
- Component and event name.
- Message.
- Typed attributes.

UTC timestamps support human investigation. Host-monotonic timestamps support local ordering and elapsed-time calculations.

Event publication checks that event identity matches the owning run.

Structured events supplement, rather than replace, detailed command receipts and evidence artifacts.

## Managed process boundary

Managed external commands use argument sequences without a shell.

PX4 receives separate retained stdout and stderr files. Its managed process runs in a new operating-system session so cleanup can target the owned process group.

Normal shutdown first requests termination with `SIGTERM`, waits for the configured interval, and escalates to `SIGKILL` if necessary.

A shutdown return code of `-15` is consistent with termination by the runtime's SIGTERM request. It is not, by itself, evidence of a flight failure.

Cleanup remains necessary after readiness, connection, mission, or analysis failures.

Abrupt host or harness termination cannot guarantee completion of cleanup or final artifact publication.

## Process readiness and vehicle readiness

Process creation does not prove simulator readiness.

The readiness mechanism searches retained output for the configured startup marker within a bounded interval. An early process exit and a readiness timeout are distinct failures.

MAVSDK discovery is a separate stage.

Vehicle preconditions are another separate stage and must pass before mission execution is authorized.

A successful environment preflight therefore does not imply that the vehicle is connected or ready to arm.

## ULog capture and landing analysis

The ULog capture path is derived from the log filename announced in the managed PX4 stdout.

Capture rejects missing or ambiguous announced paths, paths outside the expected PX4 log location, missing files, and empty files.

Capture occurs after managed simulator shutdown and publishes the retained log without overwriting an existing destination.

The captured artifact includes its SHA-256 digest and size.

Land-detection analysis reads the retained ULog and records:

- Sample count and timestamp range.
- Initial landed state.
- Observed airborne state.
- Final landed state.
- Whether a landing transition occurred.
- The landing transition timestamp when present.

This supports landing-related assertions. It is not a general flight-quality or control-performance analysis.

## Failure handling

The runtime distinguishes:

- Failed or unproven preconditions: INVALID.
- Unproven required wind activation: INVALID.
- Proven activation followed by a failed evaluated outcome assertion: FAIL.
- Infrastructure, mission-execution, or evidence-processing exceptions: ERROR.

The current executor does not automatically classify every mission abort as a vehicle-behavior failure.

Where execution progressed far enough, the runtime attempts simulator shutdown and ULog capture before publishing failure results.

If multiple failures occur, secondary cleanup, capture, or publication errors can be retained as exception notes while preserving the original failure.

Result publication is best effort on error paths. Filesystem failure or abrupt termination may prevent creation of `result.json`.

## Timing and cleanup

Host-monotonic time governs wind publication and observation budgets.

Gazebo simulation time and iteration count establish simulator progression.

PX4 boot time identifies ULog samples.

These clock domains must not be directly subtracted from one another.

The wind activation window begins at publication start, so command latency and observation latency consume the same budget.

Once publication has been attempted, delivery may be uncertain. The controller therefore attempts a bounded disable command even after certain failures or cancellation.

A disable receipt is not restoration proof. Cleanup records retain `restoration_proven: false`, and the outer runtime stops the managed simulator.

Individual stage timeouts do not constitute a guarantee that every possible filesystem operation, process-reaping operation, or abrupt termination is covered by one global wall-clock deadline.

## Dependency and import boundaries

Keep package initialization lightweight.

The runtime delays loading the wind controller at the integration boundary to avoid circular initialization through foundational runtime-file utilities.

Type-only references should not introduce unnecessary runtime imports.

New package-level re-exports must be checked in fresh interpreter processes. A complete test suite can hide an import-order problem that appears when one module is imported independently.

## Testing strategy

Software tests cover:

- Typed model validation and classification.
- Scenario and mission identity.
- Environment loading and preflight behavior.
- Exclusive artifact publication.
- Process readiness and cleanup.
- Mission lifecycle behavior with fake vehicle clients.
- Wind commands, observations, decoding, and activation assessment.
- Wind lifecycle integration with fake simulator owners.
- PASS, FAIL, and INVALID result construction.
- CLI output and exit behavior.

Synthetic tests do not prove that a real simulator satisfies a scenario.

Live PX4/Gazebo runs provide separate evidence and retain their own manifests, observations, ULogs, and results.

## Current scope and next work

The baseline path and ten-second wind variant have been demonstrated locally.

The original five-second wind requirement remains unproven. Repeatability of the ten-second variant has not yet been established.

Current limitations include:

- One pinned simulator environment.
- Single-session execution.
- No physical-aircraft support.
- Limited behavior assertions.
- No sustained wind-exposure proof.
- No directly measured aerodynamic-force proof.
- No complete implementation of the other fault scenarios.
- No completed reporting or batch-regression layer.
- No established cross-platform or unattended CI execution.

Repetition counts and seed values are retained as metadata. They do not by themselves implement repeated execution or deterministic simulation.

The next development steps are repeatability checks, accurate verification documentation, clearer reporting, and additional activation-first fault scenarios.