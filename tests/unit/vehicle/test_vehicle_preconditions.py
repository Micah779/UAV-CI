# tests for safe vehicle preconditions

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from uav_ci.vehicle import (
    ConnectedVehicle,
    VehiclePreconditionStreamEnded,
    VehiclePreconditionTimeout,
    wait_for_vehicle_preconditions,
)


OBSERVED_AT = datetime(
    2026,
    8,
    29,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeHealth:
    def __init__(self, ready: bool) -> None:
        self.is_gyrometer_calibration_ok = ready
        self.is_accelerometer_calibration_ok = ready
        self.is_magnetometer_calibration_ok = ready
        self.is_local_position_ok = ready
        self.is_global_position_ok = ready
        self.is_home_position_ok = ready
        self.is_armable = ready


class FakeLandedState:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeTelemetry:
    def __init__(
        self,
        *,
        health_values,
        armed: bool,
        landed_state: str,
    ) -> None:
        self.health_values = health_values
        self.armed_value = armed
        self.landed_state_value = landed_state

    async def health(self):
        for value in self.health_values:
            await asyncio.sleep(0)
            yield value

    async def armed(self):
        yield self.armed_value

    async def landed_state(self):
        yield FakeLandedState(
            self.landed_state_value
        )


def connected_vehicle(telemetry) -> ConnectedVehicle:
    return ConnectedVehicle(
        system=SimpleNamespace(
            telemetry=telemetry
        ),
        system_address=(
            "udpin://0.0.0.0:14540"
        ),
        elapsed_s=0.25,
    )


def test_safe_initial_state_passes() -> None:
    telemetry = FakeTelemetry(
        health_values=(
            FakeHealth(False),
            FakeHealth(True),
        ),
        armed=False,
        landed_state="ON_GROUND",
    )
    times = iter((10.0, 10.5))

    result = asyncio.run(
        wait_for_vehicle_preconditions(
            connected_vehicle(telemetry),
            timeout_s=1,
            clock=lambda: OBSERVED_AT,
            monotonic_clock=lambda: next(times),
        )
    )

    assert result.passed is True
    assert result.armable is True
    assert result.armed is False
    assert result.landed_state == "on_ground"
    assert result.elapsed_s == 0.5


@pytest.mark.parametrize(
    ("armed", "landed_state"),
    (
        (True, "ON_GROUND"),
        (False, "IN_AIR"),
    ),
)
def test_unsafe_initial_state_does_not_pass(
    armed: bool,
    landed_state: str,
) -> None:
    telemetry = FakeTelemetry(
        health_values=(FakeHealth(True),),
        armed=armed,
        landed_state=landed_state,
    )

    result = asyncio.run(
        wait_for_vehicle_preconditions(
            connected_vehicle(telemetry),
            timeout_s=1,
            clock=lambda: OBSERVED_AT,
        )
    )

    assert result.passed is False


def test_health_timeout_is_bounded() -> None:
    class NeverReadyTelemetry(FakeTelemetry):
        async def health(self):
            while True:
                await asyncio.sleep(60)

                if False:
                    yield FakeHealth(False)

    telemetry = NeverReadyTelemetry(
        health_values=(),
        armed=False,
        landed_state="ON_GROUND",
    )

    with pytest.raises(
        VehiclePreconditionTimeout,
        match="within 0.01 seconds",
    ):
        asyncio.run(
            wait_for_vehicle_preconditions(
                connected_vehicle(telemetry),
                timeout_s=0.01,
            )
        )


def test_ended_health_stream_is_rejected() -> None:
    telemetry = FakeTelemetry(
        health_values=(),
        armed=False,
        landed_state="ON_GROUND",
    )

    with pytest.raises(
        VehiclePreconditionStreamEnded,
        match="health stream ended",
    ):
        asyncio.run(
            wait_for_vehicle_preconditions(
                connected_vehicle(telemetry),
                timeout_s=1,
            )
        )


@pytest.mark.parametrize(
    "timeout_s",
    (0.0, -1.0),
)
def test_invalid_timeout_is_rejected(
    timeout_s: float,
) -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            wait_for_vehicle_preconditions(
                connected_vehicle(
                    FakeTelemetry(
                        health_values=(
                            FakeHealth(True),
                        ),
                        armed=False,
                        landed_state=(
                            "ON_GROUND"
                        ),
                    )
                ),
                timeout_s=timeout_s,
            )
        )