# managed vehicle precondition health check

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic_ns
from uav_ci.clocks import utc_now

from uav_ci.domain.enums import LogLevel
from uav_ci.runtime.files import (
    publish_text_exclusively,
)
from uav_ci.runtime.launch import (
    managed_environment,
)
from uav_ci.runtime.logging import (
    LogAttribute,
    StructuredEvent,
    append_event,
)
from uav_ci.runtime.prepare import PreparedRun
from uav_ci.vehicle import (
    VehiclePreconditionResult,
    wait_for_vehicle_preconditions,
)


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    # completed managed precondition check

    prepared_run: PreparedRun
    preconditions: VehiclePreconditionResult
    shutdown_returncode: int


async def run_health_check(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
    startup_timeout_s: float = 120.0,
    connection_timeout_s: float = 30.0,
    health_timeout_s: float = 60.0,
    clock: Callable[[], datetime] = utc_now,
    monotonic_clock: Callable[
        [],
        int,
    ] = monotonic_ns,
) -> HealthCheckResult:
    # launch and retain preflight telemetry evidence

    running = None
    preconditions = None

    async with managed_environment(
        prepared,
        px4_repository=px4_repository,
        startup_timeout_s=startup_timeout_s,
        connection_timeout_s=connection_timeout_s,
        clock=clock,
        monotonic_clock=monotonic_clock,
    ) as session:
        running = session

        preconditions = (
            await wait_for_vehicle_preconditions(
                running.vehicle,
                timeout_s=health_timeout_s,
                clock=clock,
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

        append_event(
            prepared.run_directory,
            StructuredEvent(
                timestamp=clock(),
                monotonic_ns=monotonic_clock(),
                run_id=(
                    prepared.run_directory.run_id
                ),
                scenario_id=(
                    prepared
                    .run_directory
                    .scenario_id
                ),
                level=(
                    LogLevel.INFO
                    if preconditions.passed
                    else LogLevel.WARNING
                ),
                component="vehicle",
                event=(
                    "vehicle_preconditions_evaluated"
                ),
                message=(
                    "Vehicle preconditions passed."
                    if preconditions.passed
                    else (
                        "Vehicle preconditions "
                        "did not pass."
                    )
                ),
                attributes=(
                    LogAttribute(
                        key="passed",
                        value=preconditions.passed,
                    ),
                    LogAttribute(
                        key="armed",
                        value=preconditions.armed,
                    ),
                    LogAttribute(
                        key="landed_state",
                        value=(
                            preconditions
                            .landed_state
                        ),
                    ),
                ),
            ),
        )

    if (
        running is None
        or preconditions is None
        or running.shutdown_returncode is None
    ):
        raise RuntimeError(
            "health check did not retain its result"
        )

    return HealthCheckResult(
        prepared_run=prepared,
        preconditions=preconditions,
        shutdown_returncode=(
            running.shutdown_returncode
        ),
    )