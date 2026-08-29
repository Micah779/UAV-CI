# tests for managed simulator launch sessions

import os
import asyncio
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from itertools import count
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from uav_ci.environment import (
    load_environment_profile,
)
from uav_ci.runtime import (
    LaunchRejected,
    ReadinessMatch,
    create_run_directory,
    managed_environment,
    run_launch_check,
)
from uav_ci.vehicle import ConnectedVehicle


PROJECT_ROOT = Path(__file__).parents[3]
ENVIRONMENT_PATH = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)

RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
STARTED_AT = datetime(
    2026,
    8,
    29,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_prepared_run(
    tmp_path: Path,
    *,
    ready: bool = True,
):
    run_directory = create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )

    loaded_environment = (
        load_environment_profile(
            ENVIRONMENT_PATH
        )
    )

    run_directory.environment_snapshot_path.write_text(
        loaded_environment.profile.model_dump_json(
            indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    return SimpleNamespace(
        ready=ready,
        run_directory=run_directory,
        snapshots=SimpleNamespace(
            environment_path=(
                run_directory
                .environment_snapshot_path
            ),
        ),
        manifest=SimpleNamespace(
            environment_profile=(
                loaded_environment
                .profile
                .profile_id
            ),
        ),
    )


def deterministic_clocks():
    wall_counter = count(1)
    monotonic_counter = count(1)

    wall_clock = lambda: (
        STARTED_AT
        + timedelta(
            seconds=next(wall_counter)
        )
    )
    monotonic_clock = lambda: (
        next(monotonic_counter)
        * 1_000_000_000
    )

    return wall_clock, monotonic_clock


def install_successful_runtime(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: dict[str, object] = {}

    managed = SimpleNamespace(
        process=SimpleNamespace(pid=4321),
    )

    async def fake_start(
        run_directory,
        spec,
        *,
        environment,
    ):
        calls["run_directory"] = run_directory
        calls["spec"] = spec
        calls["environment"] = environment
        return managed

    async def fake_wait(
        received_managed,
        *,
        marker,
        timeout_s,
    ):
        calls["readiness_marker"] = marker
        calls["startup_timeout_s"] = timeout_s

        return ReadinessMatch(
            process_id="px4_sitl",
            stream="stdout",
            marker=marker,
            matched_line=(
                "INFO [px4] "
                "Startup script returned successfully"
            ),
            elapsed_s=2.5,
        )

    async def fake_connect(
        system_address,
        *,
        timeout_s,
    ):
        calls["system_address"] = system_address
        calls["connection_timeout_s"] = timeout_s

        return ConnectedVehicle(
            system=SimpleNamespace(),
            system_address=system_address,
            elapsed_s=0.25,
        )

    async def fake_stop(received_managed):
        calls["stopped"] = received_managed
        return -15

    monkeypatch.setattr(
        "uav_ci.runtime.launch."
        "start_managed_process",
        fake_start,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.launch."
        "wait_for_process_readiness",
        fake_wait,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.launch."
        "connect_vehicle",
        fake_connect,
    )
    monkeypatch.setattr(
        "uav_ci.runtime.launch."
        "stop_managed_process",
        fake_stop,
    )

    return calls, managed


def event_names(prepared) -> list[str]:
    return [
        json.loads(line)["event"]
        for line in (
            prepared.run_directory.events_path
            .read_text(encoding="utf-8")
            .splitlines()
        )
    ]


def test_launch_check_composes_full_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = create_prepared_run(tmp_path)
    calls, managed = install_successful_runtime(
        monkeypatch
    )
    wall_clock, monotonic_clock = (
        deterministic_clocks()
    )

    async def exercise():
        from uav_ci.runtime.launch import (
            managed_environment,
        )

        running = None

        async with managed_environment(
            prepared,
            px4_repository=tmp_path / "PX4-Autopilot",
            startup_timeout_s=90,
            connection_timeout_s=20,
            clock=wall_clock,
            monotonic_clock=monotonic_clock,
        ) as session:
            running = session

        return running

    running = asyncio.run(exercise())

    spec = calls["spec"]

    assert spec.command == (
        "make",
        "px4_sitl",
        "gz_x500",
    )
    assert spec.cwd == (
        tmp_path / "PX4-Autopilot"
    ).resolve()
    assert spec.shutdown_timeout_s == 15

    assert calls["readiness_marker"] == (
        "Startup script returned successfully"
    )
    assert calls["startup_timeout_s"] == 90
    assert calls["system_address"] == (
        "udpin://0.0.0.0:14540"
    )
    assert calls["connection_timeout_s"] == 20
    assert calls["stopped"] is managed

    assert running.shutdown_returncode == -15

    assert event_names(prepared) == [
        "process_launch_requested",
        "process_started",
        "process_ready",
        "vehicle_connected",
        "process_stopped",
    ]

    process_environment = calls["environment"]
    expected_px4_environment = (
        tmp_path
        / "PX4-Autopilot"
        / ".venv"
    ).resolve()

    assert (
        process_environment["VIRTUAL_ENV"]
        == str(expected_px4_environment)
    )
    assert (
        process_environment["PATH"]
        .split(os.pathsep)[0]
        == str(
            expected_px4_environment / "bin"
        )
    )


def test_failed_preflight_prevents_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = create_prepared_run(
        tmp_path,
        ready=False,
    )

    async def forbidden_start(*_args, **_kwargs):
        raise AssertionError(
            "process must not start"
        )

    monkeypatch.setattr(
        "uav_ci.runtime.launch."
        "start_managed_process",
        forbidden_start,
    )

    async def exercise() -> None:
        async with managed_environment(
            prepared,
            px4_repository=tmp_path,
        ):
            pass

    with pytest.raises(
        LaunchRejected,
        match="preflight did not pass",
    ):
        asyncio.run(exercise())

    assert not (
        prepared.run_directory.events_path
        .exists()
    )


def test_operation_failure_still_stops_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = create_prepared_run(tmp_path)
    calls, managed = install_successful_runtime(
        monkeypatch
    )
    wall_clock, monotonic_clock = (
        deterministic_clocks()
    )

    async def exercise() -> None:
        async with managed_environment(
            prepared,
            px4_repository=tmp_path,
            clock=wall_clock,
            monotonic_clock=monotonic_clock,
        ):
            raise RuntimeError(
                "test operation failed"
            )

    with pytest.raises(
        RuntimeError,
        match="test operation failed",
    ):
        asyncio.run(exercise())

    assert calls["stopped"] is managed

    assert event_names(prepared) == [
        "process_launch_requested",
        "process_started",
        "process_ready",
        "vehicle_connected",
        "environment_session_failed",
        "process_stopped",
    ]