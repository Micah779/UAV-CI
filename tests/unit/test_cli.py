# tests for the UAV-CI command-line interface

from pathlib import Path
import pytest
from uav_ci.cli import main


PROJECT_ROOT = Path(__file__).parents[2]
BASELINE_SCENARIO = (
    PROJECT_ROOT / "scenarios" / "baseline.yaml"
)


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