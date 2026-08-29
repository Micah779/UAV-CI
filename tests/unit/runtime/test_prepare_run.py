# tests for complete no-flight run preparation

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.domain.environment import (
    EnvironmentProfile,
)
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.runtime import (
    EnvironmentPreflightResult,
    PreflightCheckResult,
    prepare_run,
)


PROJECT_ROOT = Path(__file__).parents[3]
SCENARIO_PATH = (
    PROJECT_ROOT / "scenarios" / "baseline.yaml"
)
ENVIRONMENT_PATH = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)
PATCH_PATH = (
    PROJECT_ROOT
    / "environments"
    / "patches"
    / "x500-enable-wind.patch"
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
TEST_HARNESS = HarnessProvenance(
    uav_ci_version="0.1.0",
    python_version="3.14.7",
    platform="test-platform",
)


def install_fake_preflight(
    monkeypatch: pytest.MonkeyPatch,
    *,
    passed: bool,
) -> None:
    def fake_preflight(
        loaded_environment,
        *,
        px4_repository,
        runner,
    ) -> EnvironmentPreflightResult:
        return EnvironmentPreflightResult(
            profile_id=(
                loaded_environment.profile.profile_id
            ),
            profile_hash=(
                loaded_environment.profile_hash
            ),
            px4_repository=Path(
                px4_repository
            ).resolve(),
            checks=(
                PreflightCheckResult(
                    check_id="test_preflight",
                    passed=passed,
                    expected="compatible",
                    observed=(
                        "compatible"
                        if passed
                        else "incompatible"
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        "uav_ci.runtime.prepare.preflight_environment",
        fake_preflight,
    )


def clock_values():
    values = iter(
        (
            STARTED_AT + timedelta(seconds=1),
            STARTED_AT + timedelta(seconds=2),
        )
    )
    return lambda: next(values)


def monotonic_values():
    values = iter((1_000_000_000, 2_000_000_000))
    return lambda: next(values)


def test_ready_run_is_fully_materialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_preflight(
        monkeypatch,
        passed=True,
    )

    prepared = prepare_run(
        SCENARIO_PATH,
        ENVIRONMENT_PATH,
        px4_repository=tmp_path / "PX4-Autopilot",
        runs_root=tmp_path / "runs",
        run_id=RUN_ID,
        started_at=STARTED_AT,
        harness=TEST_HARNESS,
        clock=clock_values(),
        monotonic_clock=monotonic_values(),
    )

    assert prepared.ready is True

    restored_manifest = RunManifest.model_validate_json(
        prepared.run_directory.manifest_path.read_text(
            encoding="utf-8"
        )
    )
    restored_scenario = ScenarioSpec.model_validate_json(
        prepared.snapshots.scenario_path.read_text(
            encoding="utf-8"
        )
    )
    restored_environment = (
        EnvironmentProfile.model_validate_json(
            prepared.snapshots.environment_path.read_text(
                encoding="utf-8"
            )
        )
    )

    assert restored_manifest == prepared.manifest
    assert restored_scenario.scenario_id == (
        "baseline_mission"
    )
    assert restored_environment.profile_id == (
        "px4-gz-x500-v1"
    )
    assert (
        prepared.snapshots.patch_paths[0].read_bytes()
        == PATCH_PATH.read_bytes()
    )

    event_names = [
        json.loads(line)["event"]
        for line in (
            prepared.run_directory.events_path
            .read_text(encoding="utf-8")
            .splitlines()
        )
    ]

    assert event_names == [
        "run_prepared",
        "preflight_completed",
    ]


def test_failed_preflight_is_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_preflight(
        monkeypatch,
        passed=False,
    )

    prepared = prepare_run(
        SCENARIO_PATH,
        ENVIRONMENT_PATH,
        px4_repository=tmp_path / "PX4-Autopilot",
        runs_root=tmp_path / "runs",
        run_id=RUN_ID,
        started_at=STARTED_AT,
        harness=TEST_HARNESS,
        clock=clock_values(),
        monotonic_clock=monotonic_values(),
    )

    assert prepared.ready is False
    assert prepared.run_directory.preflight_path.is_file()
    assert prepared.run_directory.manifest_path.is_file()

    events = [
        json.loads(line)
        for line in (
            prepared.run_directory.events_path
            .read_text(encoding="utf-8")
            .splitlines()
        )
    ]

    assert events[-1]["level"] == "warning"
    assert events[-1]["event"] == (
        "preflight_completed"
    )


def test_preparation_never_overwrites_a_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_preflight(
        monkeypatch,
        passed=True,
    )

    arguments = {
        "scenario_path": SCENARIO_PATH,
        "environment_path": ENVIRONMENT_PATH,
        "px4_repository": (
            tmp_path / "PX4-Autopilot"
        ),
        "runs_root": tmp_path / "runs",
        "run_id": RUN_ID,
        "started_at": STARTED_AT,
        "harness": TEST_HARNESS,
    }

    prepare_run(
        **arguments,
        clock=clock_values(),
        monotonic_clock=monotonic_values(),
    )

    with pytest.raises(FileExistsError):
        prepare_run(
            **arguments,
            clock=clock_values(),
            monotonic_clock=monotonic_values(),
        )