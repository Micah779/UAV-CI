# wind CLI output tests; no flight is executed

from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.cli import main
from uav_ci.domain.enums import ResultStatus
from uav_ci.faults.controller import (
    FaultActivationNotProven,
)


ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "proven",
    [
        True,
        False,
    ],
)
def test_wind_cli_reports_activation_state(
    tmp_path,
    monkeypatch,
    capsys,
    proven,
):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        '{"status": "invalid"}',
        encoding="utf-8",
    )

    prepared = SimpleNamespace(
        ready=True,
        run_directory=SimpleNamespace(
            root=tmp_path,
            result_path=result_path,
            land_detection_path=(
                tmp_path
                / "evidence"
                / "land_detection.json"
            ),
        ),
    )

    monkeypatch.setattr(
        "uav_ci.cli.prepare_run",
        lambda *args, **options: prepared,
    )

    async def flight(
        *args,
        **options,
    ):
        if not proven:
            raise FaultActivationNotProven(
                "wind was not proven"
            )

        return SimpleNamespace(
            assurance_result=SimpleNamespace(
                status=ResultStatus.PASS,
                assertions=(),
            ),
            activation=SimpleNamespace(
                activated=True,
                evidence=(
                    SimpleNamespace(
                        artifact_path=Path(
                            "evidence/wind/"
                            "activation.json"
                        ),
                    ),
                ),
            ),
            mission=SimpleNamespace(
                mission_item_count=4,
                final_current=4,
                final_total=4,
                airborne_observed=True,
                landed_observed=True,
                disarmed_observed=True,
                elapsed_s=120,
            ),
            ulog=SimpleNamespace(
                path=tmp_path / "flight.ulg",
                sha256="a" * 64,
                size_bytes=1000,
            ),
        )

    monkeypatch.setattr(
        "uav_ci.cli.run_flight_check",
        flight,
    )

    exit_code = main(
        [
            "flight-check",
            str(
                ROOT
                / "scenarios"
                / "wind.yaml"
            ),
            "--environment",
            str(
                ROOT
                / "environments"
                / "px4-gz-x500-v1.yaml"
            ),
            "--px4-repository",
            str(
                tmp_path / "PX4-Autopilot"
            ),
        ]
    )

    output = capsys.readouterr()

    if proven:
        assert exit_code == 0
        assert (
            "FLIGHT CHECK PASSED"
            in output.out
        )
        assert (
            "activation_proven: True"
            in output.out
        )
        assert (
            "activation_evidence: "
            "evidence/wind/activation.json"
            in output.out
        )
        assert output.err == ""
    else:
        assert exit_code == 1
        assert (
            "FLIGHT CHECK INVALID"
            in output.err
        )
        assert (
            f"result: {result_path}"
            in output.err
        )