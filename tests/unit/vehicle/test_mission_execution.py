# tests for bounded mission execution and recovery

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.vehicle import (
    ConnectedVehicle,
    MissionExecutionError,
    execute_mission,
)


class FakeState:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeTelemetry:
    def __init__(self) -> None:
        self.armed_calls = 0

    async def armed(self):
        self.armed_calls += 1

        if self.armed_calls == 1:
            yield True
        else:
            yield False

    async def landed_state(self):
        yield FakeState("IN_AIR")
        yield FakeState("ON_GROUND")


class FakeMissionRaw:
    def __init__(
        self,
        *,
        start_error: Exception | None = None,
    ) -> None:
        self.start_error = start_error
        self.uploaded = None

    async def import_qgroundcontrol_mission(
        self,
        path: str,
    ):
        return SimpleNamespace(
            mission_items=[object(), object()],
            geofence_items=[],
            rally_items=[],
        )

    async def upload_mission(self, items):
        self.uploaded = items

    async def start_mission(self):
        if self.start_error is not None:
            raise self.start_error

    async def mission_progress(self):
        yield SimpleNamespace(
            current=1,
            total=2,
        )
        yield SimpleNamespace(
            current=2,
            total=2,
        )


class FakeAction:
    def __init__(self) -> None:
        self.arm_called = False
        self.land_called = False
        self.disarm_called = False

    async def arm(self):
        self.arm_called = True

    async def land(self):
        self.land_called = True

    async def disarm(self):
        self.disarm_called = True


def fake_vehicle(
    mission_raw,
    action,
    telemetry,
) -> ConnectedVehicle:
    return ConnectedVehicle(
        system=SimpleNamespace(
            mission_raw=mission_raw,
            action=action,
            telemetry=telemetry,
        ),
        system_address=(
            "udpin://0.0.0.0:14540"
        ),
        elapsed_s=0.1,
    )


def test_successful_mission_lands_and_disarms(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.plan"
    mission_path.write_text(
        "{}",
        encoding="utf-8",
    )

    mission_raw = FakeMissionRaw()
    action = FakeAction()

    result = asyncio.run(
        execute_mission(
            fake_vehicle(
                mission_raw,
                action,
                FakeTelemetry(),
            ),
            mission_path,
            upload_timeout_s=1,
            completion_timeout_s=1,
        )
    )

    assert action.arm_called is True
    assert mission_raw.uploaded is not None
    assert result.mission_item_count == 2
    assert result.final_current == 2
    assert result.final_total == 2
    assert result.landed_observed is True
    assert result.disarmed_observed is True


def test_failure_after_arming_attempts_recovery(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.plan"
    mission_path.write_text(
        "{}",
        encoding="utf-8",
    )

    mission_raw = FakeMissionRaw(
        start_error=RuntimeError(
            "mission start failed"
        )
    )
    action = FakeAction()

    with pytest.raises(
        MissionExecutionError,
        match="mission execution failed",
    ):
        asyncio.run(
            execute_mission(
                fake_vehicle(
                    mission_raw,
                    action,
                    FakeTelemetry(),
                ),
                mission_path,
                upload_timeout_s=1,
                completion_timeout_s=1,
            )
        )

    assert action.arm_called is True
    assert action.land_called is True
    assert action.disarm_called is True


def test_missing_mission_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        MissionExecutionError,
        match="does not exist",
    ):
        asyncio.run(
            execute_mission(
                fake_vehicle(
                    FakeMissionRaw(),
                    FakeAction(),
                    FakeTelemetry(),
                ),
                tmp_path / "missing.plan",
                upload_timeout_s=1,
                completion_timeout_s=1,
            )
        )


def test_geofence_is_rejected_before_arming(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.plan"
    mission_path.write_text(
        "{}",
        encoding="utf-8",
    )

    mission_raw = FakeMissionRaw()

    async def import_with_geofence(path: str):
        return SimpleNamespace(
            mission_items=[object()],
            geofence_items=[object()],
            rally_items=[],
        )

    mission_raw.import_qgroundcontrol_mission = (
        import_with_geofence
    )
    action = FakeAction()

    with pytest.raises(
        MissionExecutionError,
        match="does not support",
    ):
        asyncio.run(
            execute_mission(
                fake_vehicle(
                    mission_raw,
                    action,
                    FakeTelemetry(),
                ),
                mission_path,
                upload_timeout_s=1,
                completion_timeout_s=1,
            )
        )

    assert action.arm_called is False