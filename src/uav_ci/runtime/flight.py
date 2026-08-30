# first bounded baseline SITL flight orchestration

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.runtime.files import (
    publish_text_exclusively,
)
from uav_ci.runtime.launch import (
    managed_environment,
)
from uav_ci.runtime.prepare import PreparedRun
from uav_ci.runtime.ulog import (
    CapturedULog,
    capture_px4_ulog,
)
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionResult,
    execute_mission,
    wait_for_vehicle_preconditions,
)


class FlightRejected(RuntimeError):
    # required preconditions did not authorize flight
    pass


@dataclass(frozen=True, slots=True)
class FlightCheckResult:
    # completed baseline flight check

    prepared_run: PreparedRun
    preconditions: VehiclePreconditionResult
    mission: MissionExecutionResult
    ulog: CapturedULog
    shutdown_returncode: int


def _load_snapshotted_scenario(
    prepared: PreparedRun,
) -> ScenarioSpec:
    return ScenarioSpec.model_validate_json(
        prepared.snapshots.scenario_path.read_text(
            encoding="utf-8"
        )
    )


async def run_flight_check(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
) -> FlightCheckResult:
    # execute one bounded baseline SITL flight

    scenario = _load_snapshotted_scenario(
        prepared
    )

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

    except Exception as exc:
        # Retain the original failure until PX4 has
        # stopped and ULog capture has been attempted.
        flight_error = exc

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
                raise

            flight_error.add_note(
                "ULog capture also failed: "
                f"{capture_error}"
            )

    if flight_error is not None:
        raise flight_error

    if (
        running is None
        or preconditions is None
        or mission_result is None
        or captured_ulog is None
        or running.shutdown_returncode is None
    ):
        raise RuntimeError(
            "flight check did not retain its result"
        )

    return FlightCheckResult(
        prepared_run=prepared,
        preconditions=preconditions,
        mission=mission_result,
        ulog=captured_ulog,
        shutdown_returncode=(
            running.shutdown_returncode
        ),
    )