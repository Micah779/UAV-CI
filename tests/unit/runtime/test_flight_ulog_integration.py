# tests for post-shutdown flight ULog capture

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.runtime.flight import (
    run_flight_check,
)
from uav_ci.runtime.ulog import CapturedULog
from uav_ci.vehicle import MissionExecutionResult


class FakePreconditions:
    passed = True

    def model_dump_json(
        self,
        **_kwargs,
    ) -> str:
        return "{}"


def test_ulog_is_captured_after_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    evidence_dir = run_root / "evidence"
    logs_dir = run_root / "logs"

    evidence_dir.mkdir(parents=True)
    logs_dir.mkdir()

    mission_path = run_root / "mission.plan"
    mission_path.write_text(
        "{}",
        encoding="utf-8",
    )

    run_directory = SimpleNamespace(
        vehicle_preconditions_path=(
            evidence_dir
            / "vehicle_preconditions.json"
        ),
        mission_execution_path=(
            evidence_dir
            / "mission_execution.json"
        ),
        ulog_path=logs_dir / "flight.ulg",
    )
    prepared = SimpleNamespace(
        run_directory=run_directory,
        snapshots=SimpleNamespace(
            mission_path=mission_path,
        ),
    )

    scenario = SimpleNamespace(
        execution=SimpleNamespace(
            startup_timeout_s=120,
        ),
        mission=SimpleNamespace(
            upload_timeout_s=30,
            completion_timeout_s=300,
        ),
    )

    stdout_path = logs_dir / "px4.stdout.log"
    stdout_path.write_text(
        "test stdout\n",
        encoding="utf-8",
    )

    running = SimpleNamespace(
        vehicle=object(),
        process=SimpleNamespace(
            stdout_path=stdout_path,
        ),
        shutdown_returncode=None,
    )
    lifecycle = {
        "shutdown_complete": False,
    }

    @asynccontextmanager
    async def fake_managed_environment(
        *_args,
        **_kwargs,
    ):
        try:
            yield running
        finally:
            running.shutdown_returncode = -15
            lifecycle["shutdown_complete"] = True

    async def fake_preconditions(
        *_args,
        **_kwargs,
    ):
        return FakePreconditions()

    mission_result = MissionExecutionResult(
        mission_item_count=4,
        final_current=4,
        final_total=4,
        armed_observed=True,
        airborne_observed=True,
        landed_observed=True,
        disarmed_observed=True,
        elapsed_s=120.0,
    )

    async def fake_execute_mission(
        *_args,
        **_kwargs,
    ):
        return mission_result

    captured_ulog = CapturedULog(
        path=run_directory.ulog_path,
        source_relative_path=Path(
            "log/2026-08-30/12_00_05.ulg"
        ),
        sha256="a" * 64,
        size_bytes=1024,
    )

    def fake_capture_px4_ulog(
        received_run_directory,
        *,
        px4_repository,
        process_stdout_path,
    ):
        assert lifecycle["shutdown_complete"] is True
        assert received_run_directory is run_directory
        assert px4_repository == (
            tmp_path / "PX4-Autopilot"
        )
        assert process_stdout_path == stdout_path

        return captured_ulog

    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "_load_snapshotted_scenario",
        lambda _prepared: scenario,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "managed_environment",
        fake_managed_environment,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "wait_for_vehicle_preconditions",
        fake_preconditions,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight.execute_mission",
        fake_execute_mission,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "capture_px4_ulog",
        fake_capture_px4_ulog,
    )

    result = asyncio.run(
        run_flight_check(
            prepared,
            px4_repository=(
                tmp_path / "PX4-Autopilot"
            ),
        )
    )

    assert lifecycle["shutdown_complete"] is True
    assert result.mission == mission_result
    assert result.ulog == captured_ulog
    assert result.shutdown_returncode == -15