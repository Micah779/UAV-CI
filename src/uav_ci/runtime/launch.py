# managed PX4/Gazebo launch and connection lifecycle

import os
from collections.abc import (
    AsyncIterator,
    Callable,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic_ns

from uav_ci.domain.environment import (
    EnvironmentProfile,
)
from uav_ci.domain.enums import LogLevel
from uav_ci.runtime.logging import (
    LogAttribute,
    StructuredEvent,
    append_event,
)
from uav_ci.runtime.prepare import (
    PreparedRun,
    utc_now,
)
from uav_ci.runtime.process import (
    ManagedProcess,
    ProcessSpec,
    ReadinessMatch,
    start_managed_process,
    stop_managed_process,
    wait_for_process_readiness,
)
from uav_ci.vehicle import (
    ConnectedVehicle,
    connect_vehicle,
)


PX4_STARTUP_MARKER = (
    "Startup script returned successfully"
)


class LaunchRejected(RuntimeError):
    # preparation did not authorize simulator launch
    pass


@dataclass(slots=True)
class RunningEnvironment:
    # live resources owned by one managed session

    prepared_run: PreparedRun
    process: ManagedProcess
    readiness: ReadinessMatch
    vehicle: ConnectedVehicle
    shutdown_returncode: int | None = None


@dataclass(frozen=True, slots=True)
class LaunchCheckResult:
    # retained outcome of a completed launch check

    prepared_run: PreparedRun
    readiness: ReadinessMatch
    system_address: str
    connection_elapsed_s: float
    shutdown_returncode: int


def _append_lifecycle_event(
    prepared: PreparedRun,
    *,
    event: str,
    message: str,
    clock: Callable[[], datetime],
    monotonic_clock: Callable[[], int],
    level: LogLevel = LogLevel.INFO,
    attributes: tuple[LogAttribute, ...] = (),
) -> None:
    # append one event using the prepared run identity

    run_directory = prepared.run_directory

    append_event(
        run_directory,
        StructuredEvent(
            timestamp=clock(),
            monotonic_ns=monotonic_clock(),
            run_id=run_directory.run_id,
            scenario_id=run_directory.scenario_id,
            level=level,
            component="runtime",
            event=event,
            message=message,
            attributes=attributes,
        ),
    )


def _load_snapshotted_environment(
    prepared: PreparedRun,
) -> EnvironmentProfile:
    # restore the exact environment frozen for this run

    contents = (
        prepared.snapshots.environment_path
        .read_text(encoding="utf-8")
    )

    environment = (
        EnvironmentProfile.model_validate_json(
            contents
        )
    )

    if (
        environment.profile_id
        != prepared.manifest.environment_profile
    ):
        raise ValueError(
            "snapshotted environment does not "
            "match the run manifest"
        )

    return environment

def _px4_process_environment(
    px4_repository: Path,
) -> dict[str, str]:
    # select PX4's own Python environment

    px4_virtual_environment = (
        px4_repository / ".venv"
    )
    px4_bin_directory = (
        px4_virtual_environment / "bin"
    )

    environment = os.environ.copy()

    inherited_virtual_environment = (
        environment.get("VIRTUAL_ENV")
    )
    path_entries = environment.get(
        "PATH",
        "",
    ).split(os.pathsep)

    if inherited_virtual_environment:
        inherited_bin_directory = str(
            Path(inherited_virtual_environment)
            / "bin"
        )
        path_entries = [
            entry
            for entry in path_entries
            if entry != inherited_bin_directory
        ]

    environment["VIRTUAL_ENV"] = str(
        px4_virtual_environment
    )
    environment["PATH"] = os.pathsep.join(
        (
            str(px4_bin_directory),
            *path_entries,
        )
    )

    environment.pop("PYTHONHOME", None)

    return environment


@asynccontextmanager
async def managed_environment(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
    startup_timeout_s: float = 120.0,
    connection_timeout_s: float = 30.0,
    shutdown_timeout_s: int = 15,
    clock: Callable[[], datetime] = utc_now,
    monotonic_clock: Callable[
        [],
        int,
    ] = monotonic_ns,
) -> AsyncIterator[RunningEnvironment]:
    # launch, prove, yield, and always clean up

    if not prepared.ready:
        raise LaunchRejected(
            "environment preflight did not pass"
        )

    environment = _load_snapshotted_environment(
        prepared
    )
    resolved_repository = Path(
        px4_repository
    ).resolve()

    process_environment = (
        _px4_process_environment(
            resolved_repository
        )
    )

    process_spec = ProcessSpec(
        process_id="px4_sitl",
        command=environment.px4.launch_command,
        cwd=resolved_repository,
        shutdown_timeout_s=shutdown_timeout_s,
    )

    managed: ManagedProcess | None = None
    running: RunningEnvironment | None = None

    _append_lifecycle_event(
        prepared,
        event="process_launch_requested",
        message="PX4 SITL launch was requested.",
        clock=clock,
        monotonic_clock=monotonic_clock,
        attributes=(
            LogAttribute(
                key="command",
                value=" ".join(
                    process_spec.command
                ),
            ),
        ),
    )

    try:
        managed = await start_managed_process(
            prepared.run_directory,
            process_spec,
            environment=process_environment,
        )

        _append_lifecycle_event(
            prepared,
            event="process_started",
            message="PX4 SITL process started.",
            clock=clock,
            monotonic_clock=monotonic_clock,
            attributes=(
                LogAttribute(
                    key="process_id",
                    value=process_spec.process_id,
                ),
                LogAttribute(
                    key="pid",
                    value=managed.process.pid,
                ),
            ),
        )

        readiness = (
            await wait_for_process_readiness(
                managed,
                marker=PX4_STARTUP_MARKER,
                timeout_s=startup_timeout_s,
            )
        )

        _append_lifecycle_event(
            prepared,
            event="process_ready",
            message=(
                "PX4 SITL startup readiness "
                "was proven."
            ),
            clock=clock,
            monotonic_clock=monotonic_clock,
            attributes=(
                LogAttribute(
                    key="marker",
                    value=readiness.marker,
                ),
                LogAttribute(
                    key="stream",
                    value=readiness.stream,
                ),
                LogAttribute(
                    key="elapsed_s",
                    value=readiness.elapsed_s,
                ),
            ),
        )

        vehicle = await connect_vehicle(
            environment.mavsdk.system_address,
            timeout_s=connection_timeout_s,
        )

        _append_lifecycle_event(
            prepared,
            event="vehicle_connected",
            message=(
                "MAVSDK vehicle discovery "
                "was proven."
            ),
            clock=clock,
            monotonic_clock=monotonic_clock,
            attributes=(
                LogAttribute(
                    key="system_address",
                    value=vehicle.system_address,
                ),
                LogAttribute(
                    key="elapsed_s",
                    value=vehicle.elapsed_s,
                ),
            ),
        )

        running = RunningEnvironment(
            prepared_run=prepared,
            process=managed,
            readiness=readiness,
            vehicle=vehicle,
        )

        yield running

    except BaseException as exc:
        _append_lifecycle_event(
            prepared,
            event="environment_session_failed",
            message=(
                "The managed environment session "
                "did not complete normally."
            ),
            clock=clock,
            monotonic_clock=monotonic_clock,
            level=LogLevel.ERROR,
            attributes=(
                LogAttribute(
                    key="error_type",
                    value=type(exc).__name__,
                ),
            ),
        )
        raise

    finally:
        if managed is not None:
            returncode = await stop_managed_process(
                managed
            )

            if running is not None:
                running.shutdown_returncode = (
                    returncode
                )

            _append_lifecycle_event(
                prepared,
                event="process_stopped",
                message=(
                    "PX4 SITL process group "
                    "was stopped."
                ),
                clock=clock,
                monotonic_clock=monotonic_clock,
                attributes=(
                    LogAttribute(
                        key="returncode",
                        value=returncode,
                    ),
                ),
            )


async def run_launch_check(
    prepared: PreparedRun,
    *,
    px4_repository: str | Path,
    startup_timeout_s: float = 120.0,
    connection_timeout_s: float = 30.0,
) -> LaunchCheckResult:
    # prove startup and connection, then shut down

    running: RunningEnvironment | None = None

    async with managed_environment(
        prepared,
        px4_repository=px4_repository,
        startup_timeout_s=startup_timeout_s,
        connection_timeout_s=connection_timeout_s,
    ) as session:
        running = session

    if (
        running is None
        or running.shutdown_returncode is None
    ):
        raise RuntimeError(
            "managed environment did not retain "
            "its shutdown result"
        )

    return LaunchCheckResult(
        prepared_run=prepared,
        readiness=running.readiness,
        system_address=(
            running.vehicle.system_address
        ),
        connection_elapsed_s=(
            running.vehicle.elapsed_s
        ),
        shutdown_returncode=(
            running.shutdown_returncode
        ),
    )