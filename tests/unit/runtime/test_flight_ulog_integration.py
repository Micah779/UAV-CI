# tests for classified post-flight ULog processing

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.analysis import LandDetectionSummary
from uav_ci.domain.enums import ResultStatus
from uav_ci.runtime.flight import (
    run_flight_check,
)
from uav_ci.runtime.ulog import CapturedULog
from uav_ci.vehicle import MissionExecutionResult


FINISHED_AT = datetime(
    2026,
    8,
    30,
    12,
    2,
    0,
    tzinfo=timezone.utc,
)


class FakePreconditions:
    passed = True

    def model_dump_json(
        self,
        **_kwargs,
    ) -> str:
        return "{}"


def test_flight_is_classified_after_ulog_capture(
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
        land_detection_path=(
            evidence_dir
            / "land_detection.json"
        ),
        result_path=run_root / "result.json",
        ulog_path=logs_dir / "flight.ulg",
    )
    prepared = SimpleNamespace(
        run_directory=run_directory,
        manifest=object(),
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

    land_detection = LandDetectionSummary(
        topic="vehicle_land_detected",
        instance=0,
        sample_count=100,
        first_timestamp_us=1_000_000,
        last_timestamp_us=121_000_000,
        initial_landed=True,
        airborne_observed=True,
        first_airborne_timestamp_us=(
            5_000_000
        ),
        final_landed=True,
        landing_transition_observed=True,
        landing_timestamp_us=120_000_000,
    )

    assurance_result = SimpleNamespace(
        status=ResultStatus.PASS,
        assertions=(),
    )

    def fake_capture_px4_ulog(
        received_run_directory,
        *,
        px4_repository,
        process_stdout_path,
    ):
        assert lifecycle["shutdown_complete"] is True
        assert received_run_directory is run_directory
        assert process_stdout_path == stdout_path

        return captured_ulog

    def fake_analyze_land_detection(
        received_path,
    ):
        assert received_path == captured_ulog.path
        return land_detection

    def fake_evaluate_baseline(
        received_scenario,
        received_manifest,
        *,
        preconditions,
        mission,
        land_detection,
        finished_at,
    ):
        assert received_scenario is scenario
        assert received_manifest is prepared.manifest
        assert mission is mission_result
        assert finished_at == FINISHED_AT

        return assurance_result

    def fake_write_run_result(
        received_directory,
        received_manifest,
        received_result,
    ):
        assert received_directory is run_directory
        assert received_manifest is prepared.manifest
        assert received_result is assurance_result

        return run_directory.result_path

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
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "analyze_land_detection",
        fake_analyze_land_detection,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "evaluate_baseline",
        fake_evaluate_baseline,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "write_run_result",
        fake_write_run_result,
    )

    result = asyncio.run(
        run_flight_check(
            prepared,
            px4_repository=(
                tmp_path / "PX4-Autopilot"
            ),
            clock=lambda: FINISHED_AT,
        )
    )

    assert lifecycle["shutdown_complete"] is True
    assert result.mission == mission_result
    assert result.ulog == captured_ulog
    assert (
        result.land_detection
        == land_detection
    )
    assert (
        result.assurance_result
        is assurance_result
    )
    assert result.shutdown_returncode == -15
    assert (
        run_directory
        .land_detection_path
        .is_file()
    )

def test_launch_error_is_published_before_reraise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_directory = SimpleNamespace(
        result_path=tmp_path / "result.json",
    )
    prepared = SimpleNamespace(
        run_directory=run_directory,
        manifest=object(),
        snapshots=SimpleNamespace(),
    )
    scenario = SimpleNamespace(
        execution=SimpleNamespace(
            startup_timeout_s=120,
        ),
    )

    launch_error = RuntimeError(
        "PX4 exited before readiness"
    )
    published: dict[str, object] = {}

    @asynccontextmanager
    async def failing_environment(
        *_args,
        **_kwargs,
    ):
        raise launch_error

        # This unreachable yield makes the function
        # an async context manager generator.
        yield

    def fake_write_harness_error_result(
        received_directory,
        received_manifest,
        *,
        error,
        finished_at,
    ):
        published["directory"] = (
            received_directory
        )
        published["manifest"] = (
            received_manifest
        )
        published["error"] = error
        published["finished_at"] = (
            finished_at
        )

        return SimpleNamespace(
            status=ResultStatus.ERROR,
        )

    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "_load_snapshotted_scenario",
        lambda _prepared: scenario,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "managed_environment",
        failing_environment,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.flight."
        "write_harness_error_result",
        fake_write_harness_error_result,
    )

    with pytest.raises(
        RuntimeError,
        match="PX4 exited before readiness",
    ) as exc_info:
        asyncio.run(
            run_flight_check(
                prepared,
                px4_repository=(
                    tmp_path / "PX4-Autopilot"
                ),
                clock=lambda: FINISHED_AT,
            )
        )

    assert exc_info.value is launch_error
    assert (
        published["directory"]
        is run_directory
    )
    assert (
        published["manifest"]
        is prepared.manifest
    )
    assert published["error"] is launch_error
    assert (
        published["finished_at"]
        == FINISHED_AT
    )