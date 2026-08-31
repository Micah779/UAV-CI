# tests for isolated UAV-CI run directories

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.runtime import create_run_directory


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


def test_run_directory_structure_is_created(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"

    run_directory = create_run_directory(
        runs_root,
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )

    expected_name = (
        "20260829T120000.000000Z_"
        "baseline_mission_"
        "12345678123456781234567812345678"
    )

    assert run_directory.root.name == expected_name
    assert run_directory.root.parent == runs_root.resolve()

    assert run_directory.inputs_dir.is_dir()
    assert run_directory.logs_dir.is_dir()
    assert run_directory.evidence_dir.is_dir()
    assert run_directory.reports_dir.is_dir()

    assert run_directory.manifest_path == (
        run_directory.root / "manifest.json"
    )
    assert run_directory.result_path == (
        run_directory.root / "result.json"
    )

    assert not run_directory.manifest_path.exists()
    assert not run_directory.result_path.exists()

    assert run_directory.run_id == RUN_ID
    assert run_directory.scenario_id == "baseline_mission"
    assert run_directory.started_at == STARTED_AT
    assert run_directory.events_path == (
        run_directory.logs_dir / "events.jsonl"
    )
    assert not run_directory.events_path.exists()
    assert run_directory.ulog_path == (
        run_directory.logs_dir / "flight.ulg"
    )
    assert not run_directory.ulog_path.exists()
    assert run_directory.land_detection_path == (
        run_directory.evidence_dir
        / "land_detection.json"
    )
    assert not (
        run_directory.land_detection_path.exists()
    )
    assert run_directory.input_patches_dir.is_dir()
    assert run_directory.scenario_snapshot_path == (
        run_directory.inputs_dir / "scenario.json"
    )
    assert run_directory.environment_snapshot_path == (
        run_directory.inputs_dir / "environment.json"
    )
    assert run_directory.preflight_path == (
        run_directory.evidence_dir / "preflight.json"
    )
    assert (
        run_directory.vehicle_preconditions_path
        == run_directory.evidence_dir
        / "vehicle_preconditions.json"
    )
    assert not (
        run_directory.vehicle_preconditions_path.exists()
    )
    assert run_directory.mission_snapshot_path == (
        run_directory.inputs_dir / "mission.plan"
    )
    assert not (
        run_directory.mission_snapshot_path.exists()
    )
    assert run_directory.mission_execution_path == (
        run_directory.evidence_dir
        / "mission_execution.json"
    )
    assert not (
        run_directory.mission_execution_path.exists()
    )
    assert not run_directory.scenario_snapshot_path.exists()
    assert not run_directory.environment_snapshot_path.exists()
    assert not run_directory.preflight_path.exists()

def test_existing_run_directory_is_not_overwritten(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"

    first = create_run_directory(
        runs_root,
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )

    with pytest.raises(FileExistsError):
        create_run_directory(
            runs_root,
            run_id=RUN_ID,
            scenario_id="baseline_mission",
            started_at=STARTED_AT,
        )

    assert first.root.is_dir()
    assert first.inputs_dir.is_dir()


def test_unsafe_scenario_ids_are_rejected(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"

    invalid_ids = (
        "../escape",
        "BaselineMission",
        "baseline-mission",
        "/absolute/path",
    )

    for scenario_id in invalid_ids:
        with pytest.raises(ValueError):
            create_run_directory(
                runs_root,
                run_id=RUN_ID,
                scenario_id=scenario_id,
                started_at=STARTED_AT,
            )

    assert not runs_root.exists()


def test_non_utc_timestamps_are_rejected(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"

    invalid_timestamps = (
        datetime(2026, 8, 29, 12, 0, 0),
        datetime(
            2026,
            8,
            29,
            12,
            0,
            0,
            tzinfo=timezone(
                timedelta(hours=-5)
            ),
        ),
    )

    for started_at in invalid_timestamps:
        with pytest.raises(ValueError):
            create_run_directory(
                runs_root,
                run_id=RUN_ID,
                scenario_id="baseline_mission",
                started_at=started_at,
            )

    assert not runs_root.exists()


def test_run_directory_model_is_immutable(
    tmp_path: Path,
) -> None:
    run_directory = create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(
            run_directory,
            "root",
            tmp_path / "changed",
        )