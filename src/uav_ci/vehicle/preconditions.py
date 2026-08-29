# prove safe vehicle conditions before flight

import asyncio
from collections.abc import (
    AsyncIterator,
    Callable,
)
from datetime import datetime, timedelta
from time import monotonic
from typing import Literal, Protocol, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    computed_field,
    field_validator,
)

from uav_ci.clocks import utc_now
from uav_ci.vehicle.connection import (
    ConnectedVehicle,
)


LandedStateName = Literal[
    "unknown",
    "on_ground",
    "in_air",
    "taking_off",
    "landing",
]


class HealthTelemetry(Protocol):
    is_gyrometer_calibration_ok: bool
    is_accelerometer_calibration_ok: bool
    is_magnetometer_calibration_ok: bool
    is_local_position_ok: bool
    is_global_position_ok: bool
    is_home_position_ok: bool
    is_armable: bool


class LandedStateTelemetry(Protocol):
    @property
    def name(self) -> str:
        ...


class VehicleTelemetry(Protocol):
    def health(
        self,
    ) -> AsyncIterator[HealthTelemetry]:
        ...

    def armed(
        self,
    ) -> AsyncIterator[bool]:
        ...

    def landed_state(
        self,
    ) -> AsyncIterator[LandedStateTelemetry]:
        ...


class TelemetryVehicleSystem(Protocol):
    @property
    def telemetry(self) -> VehicleTelemetry:
        ...


class VehiclePreconditionResult(BaseModel):
    # immutable evidence observed before flight

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    observed_at: AwareDatetime
    elapsed_s: float = Field(ge=0)

    gyrometer_calibration_ok: StrictBool
    accelerometer_calibration_ok: StrictBool
    magnetometer_calibration_ok: StrictBool
    local_position_ok: StrictBool
    global_position_ok: StrictBool
    home_position_ok: StrictBool
    armable: StrictBool

    armed: StrictBool
    landed_state: LandedStateName

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_use_utc(
        cls,
        value: datetime,
    ) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError(
                "observed_at must use UTC"
            )

        return value

    @computed_field
    @property
    def passed(self) -> bool:
        return all(
            (
                self.gyrometer_calibration_ok,
                self.accelerometer_calibration_ok,
                self.magnetometer_calibration_ok,
                self.local_position_ok,
                self.global_position_ok,
                self.home_position_ok,
                self.armable,
                not self.armed,
                self.landed_state == "on_ground",
            )
        )


class VehiclePreconditionError(RuntimeError):
    # base error while collecting preconditions
    pass


class VehiclePreconditionTimeout(
    VehiclePreconditionError,
    TimeoutError,
):
    # required telemetry was not proven in time
    pass


class VehiclePreconditionStreamEnded(
    VehiclePreconditionError,
):
    # a telemetry stream ended before producing evidence
    pass


def _health_is_ready(
    health: HealthTelemetry,
) -> bool:
    return all(
        (
            health.is_gyrometer_calibration_ok,
            health.is_accelerometer_calibration_ok,
            health.is_magnetometer_calibration_ok,
            health.is_local_position_ok,
            health.is_global_position_ok,
            health.is_home_position_ok,
            health.is_armable,
        )
    )


async def _first_value(
    stream: AsyncIterator[object],
    *,
    stream_name: str,
) -> object:
    try:
        return await anext(stream)
    except StopAsyncIteration as exc:
        raise VehiclePreconditionStreamEnded(
            f"{stream_name} stream ended "
            "before producing evidence"
        ) from exc


async def wait_for_vehicle_preconditions(
    connected: ConnectedVehicle,
    *,
    timeout_s: float = 60.0,
    clock: Callable[[], datetime] = utc_now,
    monotonic_clock: Callable[[], float] = monotonic,
) -> VehiclePreconditionResult:
    # wait for health, then sample ground safety state

    if timeout_s <= 0:
        raise ValueError(
            "precondition timeout must be positive"
        )

    system = cast(
        TelemetryVehicleSystem,
        connected.system,
    )
    telemetry = system.telemetry
    started = monotonic_clock()

    async def observe():
        ready_health: HealthTelemetry | None = None

        async for health in telemetry.health():
            if _health_is_ready(health):
                ready_health = health
                break

        if ready_health is None:
            raise VehiclePreconditionStreamEnded(
                "health stream ended before flight "
                "health was proven"
            )

        armed = await _first_value(
            telemetry.armed(),
            stream_name="armed",
        )
        landed_state = await _first_value(
            telemetry.landed_state(),
            stream_name="landed_state",
        )

        return (
            ready_health,
            bool(armed),
            landed_state,
        )

    try:
        health, armed, landed = (
            await asyncio.wait_for(
                observe(),
                timeout=timeout_s,
            )
        )
    except TimeoutError as exc:
        raise VehiclePreconditionTimeout(
            "vehicle preconditions were not "
            f"proven within {timeout_s} seconds"
        ) from exc
    except VehiclePreconditionError:
        raise
    except Exception as exc:
        raise VehiclePreconditionError(
            f"vehicle precondition telemetry failed: {exc}"
        ) from exc

    landed_state_name = landed.name.lower()

    valid_landed_states = {
        "unknown",
        "on_ground",
        "in_air",
        "taking_off",
        "landing",
    }

    if landed_state_name not in valid_landed_states:
        raise VehiclePreconditionError(
            "unsupported landed state: "
            f"{landed_state_name!r}"
        )

    return VehiclePreconditionResult(
        observed_at=clock(),
        elapsed_s=monotonic_clock() - started,
        gyrometer_calibration_ok=(
            health.is_gyrometer_calibration_ok
        ),
        accelerometer_calibration_ok=(
            health.is_accelerometer_calibration_ok
        ),
        magnetometer_calibration_ok=(
            health.is_magnetometer_calibration_ok
        ),
        local_position_ok=(
            health.is_local_position_ok
        ),
        global_position_ok=(
            health.is_global_position_ok
        ),
        home_position_ok=(
            health.is_home_position_ok
        ),
        armable=health.is_armable,
        armed=armed,
        landed_state=landed_state_name,
    )