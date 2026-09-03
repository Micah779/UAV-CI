# bounded baseline SITL assurance orchestration

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

from uav_ci.analysis import (
    LandDetectionSummary,
    analyze_land_detection,
    evaluate_baseline,
)
from uav_ci.analysis.wind import (
    evaluate_wind,
    validate_wind_contract,
)
from uav_ci.clocks import utc_now
from uav_ci.domain.enums import (
    ClockDomain,
    EvidenceSource,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.result import RunResult
from uav_ci.domain.scenario import (
    NoStimulusSpec,
    ScenarioSpec,
    WindStimulusSpec,
)
from uav_ci.faults.controller import (
    FaultActivationNotProven,
    FaultActivationResult,
)
from uav_ci.runtime.error_result import (
    write_harness_error_result,
)
from uav_ci.runtime.files import (
    publish_text_exclusively,
)
from uav_ci.runtime.invalid_activation import (
    write_invalid_activation_result,
)
from uav_ci.runtime.invalid_result import (
    write_invalid_precondition_result,
)
from uav_ci.runtime.launch import (
    managed_environment,
)
from uav_ci.runtime.prepare import PreparedRun
from uav_ci.runtime.result_writer import (
    write_run_result,
)
from uav_ci.runtime.ulog import (
    CapturedULog,
    capture_px4_ulog,
)
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionError,
    VehiclePreconditionResult,
    execute_mission,
    wait_for_vehicle_preconditions,
)


class FlightRejected(RuntimeError):
    # required preconditions did not authorize flight
    pass


def _wind_controller_context(
    stimulus,
    run_root,
):
    # Delayed import avoids coupling foundational
    # runtime imports back through the wind controller
    # during package initialization.
    from uav_ci.faults.wind_controller import (
        managed_wind_controller,
    )

    return managed_wind_controller(
        stimulus,
        run_root,
    )


@dataclass(frozen=True, slots=True)
class FlightCheckResult:
    # completed and classified SITL flight

    prepared_run: PreparedRun
    preconditions: VehiclePreconditionResult
    mission: MissionExecutionResult
    activation: FaultActivationResult | None
    ulog: CapturedULog
    land_detection: LandDetectionSummary
    assurance_result: RunResult
    shutdown_returncode: int


def _load_snapshotted_scenario(
    prepared: PreparedRun,
) -> ScenarioSpec:
    return ScenarioSpec.model_validate_json(
        prepared.snapshots.scenario_path.read_text(
            encoding="utf-8"
        )
    )


def _write_harness_error_safely(
    prepared: PreparedRun,
    error: Exception,
    *,
    clock: Callable[[], datetime],
) -> None:
    # retain the original exception if publication fails

    try:
        write_harness_error_result(
            prepared.run_directory,
            prepared.manifest,
            error=error,
            finished_at=clock(),
        )
    except Exception as publication_error:
        error.add_note(
            "result publication also failed: "
            f"{publication_error}"
        )


def _write_vehicle_invalid_safely(
    prepared: PreparedRun,
    error: Exception,
    preconditions: (
        VehiclePreconditionResult | None
    ),
    *,
    clock: Callable[[], datetime],
) -> None:
    # publish failed or unproven vehicle readiness

    try:
        finished_at = clock()
        evidence: tuple[EvidenceRef, ...] = ()

        if preconditions is not None:
            evidence = (
                EvidenceRef(
                    source=(
                        EvidenceSource.TELEMETRY
                    ),
                    clock_domain=ClockDomain.UTC,
                    timestamp_us=int(
                        preconditions
                        .observed_at
                        .timestamp()
                        * 1_000_000
                    ),
                    signal=(
                        "vehicle.preconditions.passed"
                    ),
                    artifact_path=Path(
                        "evidence/"
                        "vehicle_preconditions.json"
                    ),
                    description=(
                        "MAVSDK telemetry recorded "
                        "the preflight vehicle state."
                    ),
                ),
            )

        message = (
            "Vehicle preconditions did not pass."
            if preconditions is not None
            else (
                "Vehicle preconditions were not "
                f"proven: {error}"
            )
        )

        write_invalid_precondition_result(
            prepared.run_directory,
            prepared.manifest,
            assertion_id="vehicle_ready",
            message=message,
            finished_at=finished_at,
            evidence=evidence,
        )

    except Exception as publication_error:
        error.add_note(
            "invalid result publication also "
            f"failed: {publication_error}"
        )


async def run_flight_check(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
    clock: Callable[
        [],
        datetime,
    ] = utc_now,
) -> FlightCheckResult:
    # execute and classify one SITL run

    try:
        scenario = _load_snapshotted_scenario(
            prepared
        )

        if isinstance(
            scenario.stimulus,
            WindStimulusSpec,
        ):
            validate_wind_contract(
                scenario,
                prepared.manifest,
            )
        elif not isinstance(
            scenario.stimulus,
            NoStimulusSpec,
        ):
            raise ValueError(
                "flight-check currently supports "
                "baseline and wind only"
            )

    except Exception as error:
        _write_harness_error_safely(
            prepared,
            error,
            clock=clock,
        )
        raise

    running = None
    preconditions = None
    mission_result = None
    captured_ulog = None
    activation_result = None
    fault_lifecycle = None
    flight_error: Exception | None = None
    cancellation: (
        asyncio.CancelledError | None
    ) = None

    try:
        async with managed_environment(
            prepared,
            px4_repository=px4_repository,
            startup_timeout_s=(
                scenario
                .execution
                .startup_timeout_s
            ),
        ) as session:
            running = session

            preconditions = (
                await wait_for_vehicle_preconditions(
                    running.vehicle,
                    timeout_s=60,
                )
            )

            publish_text_exclusively(
                prepared
                .run_directory
                .vehicle_preconditions_path,
                preconditions.model_dump_json(
                    indent=2,
                    exclude_computed_fields=True,
                )
                + "\n",
            )

            if not preconditions.passed:
                raise FlightRejected(
                    "vehicle preconditions did not pass"
                )

            async def fly(
                on_airborne=None,
            ):
                return await execute_mission(
                    running.vehicle,
                    prepared.snapshots.mission_path,
                    upload_timeout_s=(
                        scenario
                        .mission
                        .upload_timeout_s
                    ),
                    completion_timeout_s=(
                        scenario
                        .mission
                        .completion_timeout_s
                    ),
                    on_airborne=on_airborne,
                )

            def record_mission() -> None:
                assert mission_result is not None

                publish_text_exclusively(
                    prepared
                    .run_directory
                    .mission_execution_path,
                    json.dumps(
                        asdict(mission_result),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )

            if isinstance(
                scenario.stimulus,
                WindStimulusSpec,
            ):
                async with _wind_controller_context(
                    scenario.stimulus,
                    prepared.run_directory.root,
                ) as fault:
                    fault_lifecycle = fault

                    async def activate_wind() -> None:
                        nonlocal activation_result

                        await fault.activate()
                        activation_result = (
                            await fault
                            .prove_activation()
                        )

                    mission_result = await fly(
                        activate_wind
                    )
                    record_mission()
            else:
                mission_result = await fly()
                record_mission()

    except asyncio.CancelledError as error:
        cancellation = error
        flight_error = RuntimeError(
            "flight check cancelled"
        )

        for note in getattr(
            error,
            "__notes__",
            (),
        ):
            flight_error.add_note(note)

    except Exception as error:
        # Preserve the original failure until PX4
        # shutdown and ULog capture are attempted.
        flight_error = error

    if (
        running is not None
        and running.shutdown_returncode is not None
    ):
        try:
            captured_ulog = capture_px4_ulog(
                prepared.run_directory,
                px4_repository=px4_repository,
                process_stdout_path=(
                    running.process.stdout_path
                ),
            )
        except Exception as capture_error:
            if flight_error is None:
                flight_error = capture_error
            else:
                flight_error.add_note(
                    "ULog capture also failed: "
                    f"{capture_error}"
                )

    if (
        flight_error is None
        and fault_lifecycle is not None
    ):
        try:
            fault_lifecycle.require_activation_proven()
        except FaultActivationNotProven as error:
            flight_error = error

    if flight_error is not None:
        if (
            isinstance(
                flight_error,
                FaultActivationNotProven,
            )
            and preconditions is not None
            and activation_result is not None
        ):
            try:
                write_invalid_activation_result(
                    prepared.run_directory,
                    prepared.manifest,
                    assertion_id=(
                        "wind_reached_vehicle"
                    ),
                    preconditions=preconditions,
                    activation=activation_result,
                    finished_at=clock(),
                )
            except Exception as publication_error:
                publication_error.add_note(
                    "activation was also "
                    f"unproven: {flight_error}"
                )
                flight_error = publication_error

                _write_harness_error_safely(
                    prepared,
                    flight_error,
                    clock=clock,
                )

        elif isinstance(
            flight_error,
            (
                FlightRejected,
                VehiclePreconditionError,
            ),
        ):
            _write_vehicle_invalid_safely(
                prepared,
                flight_error,
                preconditions,
                clock=clock,
            )
        else:
            _write_harness_error_safely(
                prepared,
                flight_error,
                clock=clock,
            )

        if cancellation is not None:
            raise cancellation

        raise flight_error

    if (
        running is None
        or preconditions is None
        or mission_result is None
        or captured_ulog is None
        or running.shutdown_returncode is None
    ):
        incomplete_error = RuntimeError(
            "flight check did not retain its "
            "execution evidence"
        )

        _write_harness_error_safely(
            prepared,
            incomplete_error,
            clock=clock,
        )

        raise incomplete_error

    try:
        land_detection = analyze_land_detection(
            captured_ulog.path
        )

        publish_text_exclusively(
            prepared
            .run_directory
            .land_detection_path,
            json.dumps(
                asdict(land_detection),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        if activation_result is None:
            assurance_result = evaluate_baseline(
                scenario,
                prepared.manifest,
                preconditions=preconditions,
                mission=mission_result,
                land_detection=land_detection,
                finished_at=clock(),
            )
        else:
            assurance_result = evaluate_wind(
                scenario,
                prepared.manifest,
                preconditions=preconditions,
                activation=activation_result,
                mission=mission_result,
                land_detection=land_detection,
                finished_at=clock(),
            )

        write_run_result(
            prepared.run_directory,
            prepared.manifest,
            assurance_result,
        )

    except Exception as error:
        _write_harness_error_safely(
            prepared,
            error,
            clock=clock,
        )
        raise

    return FlightCheckResult(
        prepared_run=prepared,
        preconditions=preconditions,
        mission=mission_result,
        activation=activation_result,
        ulog=captured_ulog,
        land_detection=land_detection,
        assurance_result=assurance_result,
        shutdown_returncode=(
            running.shutdown_returncode
        ),
    )