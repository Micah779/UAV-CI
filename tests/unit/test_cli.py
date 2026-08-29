# tests for the UAV-CI command-line interface

from pathlib import Path
import pytest
from uav_ci.cli import main
from uav_ci.runtime import (
    EnvironmentPreflightResult,
    PreflightCheckResult,
)
from uav_ci.vehicle import (
    ConnectedVehicle,
    VehicleConnectionTimeout,
)
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).parents[2]
BASELINE_SCENARIO = (
    PROJECT_ROOT / "scenarios" / "baseline.yaml"
)
ENVIRONMENT_PROFILE = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)
TEST_PX4_REPOSITORY = Path(
    "/tmp/PX4-Autopilot"
)
ENVIRONMENT_HASH = "c" * 64


def test_validate_command_accepts_valid_scenario(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "validate",
            str(BASELINE_SCENARIO),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "VALID: baseline_mission" in captured.out
    assert "activation_required: false" in captured.out
    assert "assertions: 1" in captured.out
    assert "hash: " in captured.out
    assert captured.err == ""


def test_validate_command_rejects_invalid_scenario(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(
        "schema_version: 2\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "validate",
            str(invalid_path),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "INVALID:" in captured.err
    assert "scenario validation failed" in captured.err


def test_missing_subcommand_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2


# test result helper
def preflight_result(
    *,
    check_passed: bool,
) -> EnvironmentPreflightResult:
    return EnvironmentPreflightResult(
        profile_id="px4-gz-x500-v1",
        profile_hash=ENVIRONMENT_HASH,
        px4_repository=TEST_PX4_REPOSITORY,
        checks=(
            PreflightCheckResult(
                check_id="px4_revision_matches",
                passed=check_passed,
                expected="expected-revision",
                observed=(
                    "expected-revision"
                    if check_passed
                    else "different-revision"
                ),
                command=(
                    "git",
                    "rev-parse",
                    "HEAD",
                ),
            ),
        ),
    )


# successful preflight test
def test_preflight_command_reports_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_preflight(
        *_args: object,
        **_kwargs: object,
    ) -> EnvironmentPreflightResult:
        return preflight_result(
            check_passed=True
        )

    monkeypatch.setattr(
        "uav_ci.cli.preflight_environment",
        fake_preflight,
    )

    exit_code = main(
        [
            "preflight",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "profile: px4-gz-x500-v1" in captured.out
    assert f"hash: {ENVIRONMENT_HASH}" in captured.out
    assert (
        "[PASS] px4_revision_matches"
        in captured.out
    )
    assert "PREFLIGHT PASSED" in captured.out
    assert captured.err == ""


# failed preflight test
def test_preflight_command_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_preflight(
        *_args: object,
        **_kwargs: object,
    ) -> EnvironmentPreflightResult:
        return preflight_result(
            check_passed=False
        )

    monkeypatch.setattr(
        "uav_ci.cli.preflight_environment",
        fake_preflight,
    )

    exit_code = main(
        [
            "preflight",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert (
        "[FAIL] px4_revision_matches"
        in captured.out
    )
    assert "different-revision" in captured.out
    assert "PREFLIGHT FAILED" in captured.out
    assert captured.err == ""


# invalid profile test
def test_preflight_command_rejects_invalid_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_profile = (
        tmp_path / "missing-environment.yaml"
    )

    exit_code = main(
        [
            "preflight",
            str(missing_profile),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "INVALID ENVIRONMENT:" in captured.err

def test_prepare_command_reports_ready_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    fake_run_directory = SimpleNamespace(
        root=tmp_path / "run",
        manifest_path=tmp_path / "run/manifest.json",
        preflight_path=tmp_path / "run/evidence/preflight.json",
    )
    fake_prepared = SimpleNamespace(
        manifest=SimpleNamespace(
            scenario_id="baseline_mission"
        ),
        run_directory=fake_run_directory,
        ready=True,
    )

    monkeypatch.setattr(
        "uav_ci.cli.prepare_run",
        lambda *_args, **_kwargs: fake_prepared,
    )

    exit_code = main(
        [
            "prepare",
            str(BASELINE_SCENARIO),
            "--environment",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
            "--runs-root",
            str(tmp_path / "runs"),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "PREPARED: baseline_mission" in captured.out
    assert "ready: true" in captured.out


def test_prepare_command_reports_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    fake_prepared = SimpleNamespace(
        manifest=SimpleNamespace(
            scenario_id="baseline_mission"
        ),
        run_directory=SimpleNamespace(
            root=tmp_path / "run",
            manifest_path=tmp_path / "run/manifest.json",
            preflight_path=(
                tmp_path / "run/evidence/preflight.json"
            ),
        ),
        ready=False,
    )

    monkeypatch.setattr(
        "uav_ci.cli.prepare_run",
        lambda *_args, **_kwargs: fake_prepared,
    )

    exit_code = main(
        [
            "prepare",
            str(BASELINE_SCENARIO),
            "--environment",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ready: false" in captured.out

def test_connect_check_reports_proven_connection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_connect_vehicle(
        system_address: str,
        *,
        timeout_s: float,
    ) -> ConnectedVehicle:
        assert system_address == "udpin://0.0.0.0:14540"
        assert timeout_s == 12.0

        return ConnectedVehicle(
            system=SimpleNamespace(),
            system_address=system_address,
            elapsed_s=0.25,
        )

    monkeypatch.setattr(
        "uav_ci.cli.connect_vehicle",
        fake_connect_vehicle,
    )

    exit_code = main(
        [
            "connect-check",
            str(ENVIRONMENT_PROFILE),
            "--timeout-seconds",
            "12",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "CONNECTION PROVED" in captured.out
    assert "system_address: udpin://0.0.0.0:14540" in (
        captured.out
    )
    assert "elapsed_seconds: 0.250" in (
        captured.out
    )
    assert captured.err == ""


def test_connect_check_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_connect_vehicle(
        system_address: str,
        *,
        timeout_s: float,
    ) -> ConnectedVehicle:
        raise VehicleConnectionTimeout(
            "test connection timeout"
        )

    monkeypatch.setattr(
        "uav_ci.cli.connect_vehicle",
        fake_connect_vehicle,
    )

    exit_code = main(
        [
            "connect-check",
            str(ENVIRONMENT_PROFILE),
            "--timeout-seconds",
            "1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "CONNECTION FAILED:" in captured.err
    assert "test connection timeout" in (
        captured.err
    )

def test_launch_check_command_reports_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    prepared = SimpleNamespace(
        ready=True,
        run_directory=SimpleNamespace(
            root=tmp_path / "run",
        ),
    )

    monkeypatch.setattr(
        "uav_ci.cli.prepare_run",
        lambda *_args, **_kwargs: prepared,
    )

    async def fake_launch_check(
        received_prepared,
        *,
        px4_repository,
        startup_timeout_s,
        connection_timeout_s,
    ):
        assert received_prepared is prepared
        assert startup_timeout_s == 90.0
        assert connection_timeout_s == 20.0

        return SimpleNamespace(
            readiness=SimpleNamespace(
                elapsed_s=2.5
            ),
            connection_elapsed_s=0.25,
            shutdown_returncode=-15,
        )

    monkeypatch.setattr(
        "uav_ci.cli.run_launch_check",
        fake_launch_check,
    )

    exit_code = main(
        [
            "launch-check",
            str(BASELINE_SCENARIO),
            "--environment",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
            "--runs-root",
            str(tmp_path / "runs"),
            "--startup-timeout-seconds",
            "90",
            "--connection-timeout-seconds",
            "20",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "LAUNCH CHECK PASSED" in captured.out
    assert (
        "startup_elapsed_seconds: 2.500"
        in captured.out
    )
    assert (
        "connection_elapsed_seconds: 0.250"
        in captured.out
    )
    assert "shutdown_returncode: -15" in (
        captured.out
    )
    assert captured.err == ""


def test_launch_check_rejects_failed_preflight(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    prepared = SimpleNamespace(
        ready=False,
        run_directory=SimpleNamespace(
            root=tmp_path / "run",
        ),
    )

    monkeypatch.setattr(
        "uav_ci.cli.prepare_run",
        lambda *_args, **_kwargs: prepared,
    )

    exit_code = main(
        [
            "launch-check",
            str(BASELINE_SCENARIO),
            "--environment",
            str(ENVIRONMENT_PROFILE),
            "--px4-repository",
            str(TEST_PX4_REPOSITORY),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "LAUNCH REJECTED" in captured.err