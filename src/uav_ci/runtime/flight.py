# bounded baseline SITL assurance orchestration

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
from uav_ci.clocks import utc_now
from uav_ci.domain.result import RunResult
from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.runtime.error_result import (
    write_harness_error_result,
)
from uav_ci.runtime.files import (
    publish_text_exclusively,
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


@dataclass(frozen=True, slots=True)
class FlightCheckResult:
    # completed and classified baseline flight

    prepared_run: PreparedRun
    preconditions: VehiclePreconditionResult
    mission: MissionExecutionResult
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


async def run_flight_check(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
    clock: Callable[
        [],
        datetime,
    ] = utc_now,
) -> FlightCheckResult:
    # execute and classify one baseline SITL run

    try:
        scenario = _load_snapshotted_scenario(
            prepared
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
    flight_error: Exception | None = None

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

            mission_result = await execute_mission(
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
            )

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

    if flight_error is not None:
        # Preconditions are not harness errors. They
        # will receive INVALID results separately.
        if not isinstance(
            flight_error,
            (
                FlightRejected,
                VehiclePreconditionError,
            ),
        ):
            _write_harness_error_safely(
                prepared,
                flight_error,
                clock=clock,
            )

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

        assurance_result = evaluate_baseline(
            scenario,
            prepared.manifest,
            preconditions=preconditions,
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
        ulog=captured_ulog,
        land_detection=land_detection,
        assurance_result=assurance_result,
        shutdown_returncode=(
            running.shutdown_returncode
        ),
    )