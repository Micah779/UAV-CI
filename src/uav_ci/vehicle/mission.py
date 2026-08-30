# bounded MAVSDK mission execution with recovery

import asyncio
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol, TypeVar, cast


T = TypeVar("T")


class MissionProgressTelemetry(Protocol):
    current: int
    total: int


class MissionImportData(Protocol):
    mission_items: list[object]
    geofence_items: list[object]
    rally_items: list[object]


class MissionRawClient(Protocol):
    async def import_qgroundcontrol_mission(
        self,
        qgc_plan_path: str,
    ) -> MissionImportData:
        ...

    async def upload_mission(
        self,
        mission_items: list[object],
    ) -> None:
        ...

    async def set_current_mission_item(
        self,
        index: int,
    ) -> None:
        ...

    async def start_mission(self) -> None:
        ...

    def mission_progress(
        self,
    ) -> AsyncIterator[MissionProgressTelemetry]:
        ...


class ActionClient(Protocol):
    async def arm(self) -> None:
        ...

    async def land(self) -> None:
        ...

    async def disarm(self) -> None:
        ...


class LandedStateTelemetry(Protocol):
    @property
    def name(self) -> str:
        ...


class MissionTelemetry(Protocol):
    def armed(self) -> AsyncIterator[bool]:
        ...

    def landed_state(
        self,
    ) -> AsyncIterator[LandedStateTelemetry]:
        ...


class MissionVehicleSystem(Protocol):
    @property
    def mission_raw(self) -> MissionRawClient:
        ...

    @property
    def action(self) -> ActionClient:
        ...

    @property
    def telemetry(self) -> MissionTelemetry:
        ...


@dataclass(frozen=True, slots=True)
class MissionExecutionResult:
    # successful mission execution evidence

    mission_item_count: int
    final_current: int
    final_total: int
    armed_observed: bool
    airborne_observed: bool
    landed_observed: bool
    disarmed_observed: bool
    elapsed_s: float


class MissionExecutionError(RuntimeError):
    # base mission execution error
    pass


class MissionExecutionTimeout(
    MissionExecutionError,
    TimeoutError,
):
    # a bounded mission operation timed out
    pass


class MissionTelemetryStreamEnded(
    MissionExecutionError,
):
    # required telemetry ended before proof
    pass


async def _bounded(
    operation: Awaitable[T],
    *,
    timeout_s: float,
    operation_name: str,
) -> T:
    try:
        return await asyncio.wait_for(
            operation,
            timeout=timeout_s,
        )
    except TimeoutError as exc:
        raise MissionExecutionTimeout(
            f"{operation_name} did not complete "
            f"within {timeout_s} seconds"
        ) from exc


async def _wait_for_armed_state(
    telemetry: MissionTelemetry,
    *,
    expected: bool,
) -> bool:
    async for armed in telemetry.armed():
        if armed is expected:
            return armed

    raise MissionTelemetryStreamEnded(
        "armed telemetry ended before observing "
        f"{expected}"
    )


async def _wait_for_airborne_state(
    telemetry: MissionTelemetry,
) -> bool:
    async for state in telemetry.landed_state():
        if state.name.lower() == "in_air":
            return True

    raise MissionTelemetryStreamEnded(
        "landed-state telemetry ended before "
        "observing in_air"
    )


async def _wait_for_landed_state(
    telemetry: MissionTelemetry,
) -> bool:
    async for state in telemetry.landed_state():
        if state.name.lower() == "on_ground":
            return True

    raise MissionTelemetryStreamEnded(
        "landed-state telemetry ended before "
        "observing on_ground"
    )


async def _wait_for_mission_completion(
    mission_raw: MissionRawClient,
) -> MissionProgressTelemetry:
    async for progress in (
        mission_raw.mission_progress()
    ):
        if (
            progress.total > 0
            and progress.current >= progress.total
        ):
            return progress

    raise MissionTelemetryStreamEnded(
        "mission progress ended before completion"
    )


async def _attempt_landing_recovery(
    system: MissionVehicleSystem,
    *,
    timeout_s: float,
) -> None:
    # best-effort recovery without masking original error

    try:
        await _bounded(
            system.action.land(),
            timeout_s=10,
            operation_name="recovery land command",
        )
    except Exception:
        pass

    try:
        await _bounded(
            _wait_for_landed_state(
                system.telemetry
            ),
            timeout_s=timeout_s,
            operation_name="recovery landing",
        )
    except Exception:
        return

    try:
        await _bounded(
            system.action.disarm(),
            timeout_s=10,
            operation_name="recovery disarm",
        )
    except Exception:
        pass


async def execute_mission(
    connected: object,
    mission_path: str | Path,
    *,
    upload_timeout_s: float,
    completion_timeout_s: float,
    recovery_timeout_s: float = 90.0,
    monotonic_clock: Callable[
        [],
        float,
    ] = monotonic,
) -> MissionExecutionResult:
    # upload and execute one snapshotted mission

    if upload_timeout_s <= 0:
        raise ValueError(
            "upload timeout must be positive"
        )

    if completion_timeout_s <= 0:
        raise ValueError(
            "completion timeout must be positive"
        )

    if recovery_timeout_s <= 0:
        raise ValueError(
            "recovery timeout must be positive"
        )

    from uav_ci.vehicle.connection import (
        ConnectedVehicle,
    )

    if not isinstance(connected, ConnectedVehicle):
        raise TypeError(
            "connected must be a ConnectedVehicle"
        )

    resolved_mission = Path(
        mission_path
    ).resolve()

    if not resolved_mission.is_file():
        raise MissionExecutionError(
            "snapshotted mission does not exist: "
            f"{resolved_mission}"
        )

    system = cast(
        MissionVehicleSystem,
        connected.system,
    )
    started = monotonic_clock()

    async def import_and_upload() -> int:
        imported = (
            await system
            .mission_raw
            .import_qgroundcontrol_mission(
                str(resolved_mission)
            )
        )

        if not imported.mission_items:
            raise MissionExecutionError(
                "imported mission contains no items"
            )

        if (
            imported.geofence_items
            or imported.rally_items
        ):
            raise MissionExecutionError(
                "initial release does not support "
                "mission geofences or rally points"
            )

        await system.mission_raw.upload_mission(
            imported.mission_items
        )

        return len(imported.mission_items)

    try:
        mission_item_count = await _bounded(
            import_and_upload(),
            timeout_s=upload_timeout_s,
            operation_name="mission import and upload",
        )
    except MissionExecutionError:
        raise
    except Exception as exc:
        raise MissionExecutionError(
            f"mission import or upload failed: {exc}"
        ) from exc

    # PX4 can retain the final mission index between
    # simulator runs. Explicitly restart from item zero.
    try:
        await _bounded(
            system
            .mission_raw
            .set_current_mission_item(0),
            timeout_s=10,
            operation_name="mission cursor reset",
        )
    except MissionExecutionError:
        raise
    except Exception as exc:
        raise MissionExecutionError(
            f"mission cursor reset failed: {exc}"
        ) from exc

    arm_command_accepted = False

    try:
        await _bounded(
            system.action.arm(),
            timeout_s=15,
            operation_name="arm command",
        )
        arm_command_accepted = True

        armed_observed = await _bounded(
            _wait_for_armed_state(
                system.telemetry,
                expected=True,
            ),
            timeout_s=15,
            operation_name="armed-state proof",
        )

        await _bounded(
            system.mission_raw.start_mission(),
            timeout_s=15,
            operation_name="mission start",
        )

        # Mission completion cannot be accepted until
        # the vehicle has actually left the ground.
        airborne_observed = await _bounded(
            _wait_for_airborne_state(
                system.telemetry
            ),
            timeout_s=30,
            operation_name="airborne-state proof",
        )

        async def complete_and_land():
            progress = (
                await _wait_for_mission_completion(
                    system.mission_raw
                )
            )

            landed = await _wait_for_landed_state(
                system.telemetry
            )

            await _wait_for_armed_state(
                system.telemetry,
                expected=False,
            )
            disarmed = True

            return progress, landed, disarmed

        progress, landed, disarmed = await _bounded(
            complete_and_land(),
            timeout_s=completion_timeout_s,
            operation_name=(
                "mission completion and landing"
            ),
        )

    except Exception as exc:
        if arm_command_accepted:
            await _attempt_landing_recovery(
                system,
                timeout_s=recovery_timeout_s,
            )

        if isinstance(exc, MissionExecutionError):
            raise

        raise MissionExecutionError(
            f"mission execution failed: {exc}"
        ) from exc

    return MissionExecutionResult(
        mission_item_count=mission_item_count,
        final_current=progress.current,
        final_total=progress.total,
        armed_observed=armed_observed,
        airborne_observed=airborne_observed,
        landed_observed=landed,
        disarmed_observed=disarmed,
        elapsed_s=monotonic_clock() - started,
    )