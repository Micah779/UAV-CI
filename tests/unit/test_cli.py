# tests for the UAV-CI command-line interface

from pathlib import Path
import pytest
from uav_ci.cli import main
from uav_ci.runtime import (
    EnvironmentPreflightResult,
    PreflightCheckResult,
)


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