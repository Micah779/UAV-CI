# create isolated filesystem locations for UAV-CI runs

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import re
from uuid import UUID


SCENARIO_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*$"
)


@dataclass(frozen=True, slots=True)
class RunDirectory:
    # filesystem locations owned by one UAV-CI run

    run_id: UUID
    scenario_id: str
    started_at: datetime

    root: Path
    inputs_dir: Path
    logs_dir: Path
    evidence_dir: Path
    reports_dir: Path
    workspace_dir: Path
    events_path: Path
    ulog_path: Path
    land_detection_path: Path
    manifest_path: Path
    result_path: Path
    input_patches_dir: Path
    scenario_snapshot_path: Path
    environment_snapshot_path: Path
    preflight_path: Path
    vehicle_preconditions_path: Path
    mission_snapshot_path: Path
    mission_execution_path: Path

def create_run_directory(
    runs_root: str | Path,
    *,
    run_id: UUID,
    scenario_id: str,
    started_at: datetime,
) -> RunDirectory:
    # create a new, non-overwriting run directory

    if SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None:
        raise ValueError(
            "scenario_id must use lowercase letters, "
            "numbers, and underscores"
        )

    if started_at.tzinfo is None:
        raise ValueError(
            "started_at must be timezone-aware"
        )

    if started_at.utcoffset() != timedelta(0):
        raise ValueError(
            "started_at must use UTC"
        )

    timestamp = started_at.strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    directory_name = (
        f"{timestamp}_{scenario_id}_{run_id.hex}"
    )

    root = Path(runs_root).resolve() / directory_name

    # exist_ok=False prevents accidental reuse or overwrite.
    root.mkdir(
        parents=True,
        exist_ok=False,
    )

    inputs_dir = root / "inputs"
    logs_dir = root / "logs"
    evidence_dir = root / "evidence"
    reports_dir = root / "reports"
    workspace_dir = root / "workspace"
    input_patches_dir = inputs_dir / "patches"

    for directory in (
        inputs_dir,
        workspace_dir,
        logs_dir,
        evidence_dir,
        reports_dir,
    ):
        directory.mkdir()

    input_patches_dir.mkdir()

    return RunDirectory(
        run_id=run_id,
        scenario_id=scenario_id,
        started_at=started_at,
        root=root,
        inputs_dir=inputs_dir,
        input_patches_dir=input_patches_dir,
        logs_dir=logs_dir,
        evidence_dir=evidence_dir,
        workspace_dir=workspace_dir,
        reports_dir=reports_dir,
        scenario_snapshot_path=(
            inputs_dir / "scenario.json"
        ),
        environment_snapshot_path=(
            inputs_dir / "environment.json"
        ),
        preflight_path=(
            evidence_dir / "preflight.json"
        ),
        events_path=logs_dir / "events.jsonl",
        ulog_path=logs_dir / "flight.ulg",
        land_detection_path=(
            evidence_dir / "land_detection.json"
        ),
        manifest_path=root / "manifest.json",
        result_path=root / "result.json",
        vehicle_preconditions_path=(
            evidence_dir / "vehicle_preconditions.json"
        ),
        mission_snapshot_path=(
            inputs_dir / "mission.plan"
        ),
        mission_execution_path=(
            evidence_dir / "mission_execution.json"
        ),
    )