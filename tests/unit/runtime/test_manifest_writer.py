# tests for building and writing run manifests

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.runtime import (
    build_run_manifest,
    create_run_directory,
    detect_harness_provenance,
    write_run_manifest,
)
from uav_ci.scenario import load_scenario


PROJECT_ROOT = Path(__file__).parents[3]
BASELINE_SCENARIO = (
    PROJECT_ROOT / "scenarios" / "baseline.yaml"
)

RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
OTHER_RUN_ID = UUID(
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
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


def build_test_context(tmp_path: Path):
    loaded = load_scenario(BASELINE_SCENARIO)

    run_directory = create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id=loaded.scenario.scenario_id,
        started_at=STARTED_AT,
    )

    manifest = build_run_manifest(
        loaded,
        run_id=RUN_ID,
        started_at=STARTED_AT,
        repetition_index=1,
        harness=TEST_HARNESS,
    )

    return run_directory, manifest


def test_manifest_is_built_from_loaded_scenario(
    tmp_path: Path,
) -> None:
    run_directory, manifest = build_test_context(
        tmp_path
    )

    assert manifest.run_id == run_directory.run_id
    assert manifest.scenario_id == "baseline_mission"
    assert manifest.environment_profile == (
        "px4-gz-x500-v1"
    )
    assert manifest.requires_activation is False
    assert manifest.repetition_index == 1
    assert manifest.repetition_count == 1
    assert manifest.seed == 42
    assert manifest.harness == TEST_HARNESS


def test_real_harness_provenance_is_detected() -> None:
    provenance = detect_harness_provenance()

    assert provenance.uav_ci_version
    assert provenance.python_version
    assert provenance.platform


def test_manifest_is_written_as_valid_json(
    tmp_path: Path,
) -> None:
    run_directory, manifest = build_test_context(
        tmp_path
    )

    manifest_path = write_run_manifest(
        run_directory,
        manifest,
    )

    restored = RunManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    assert manifest_path == run_directory.manifest_path
    assert restored == manifest
    assert list(
        run_directory.root.glob(
            ".manifest.json.*.tmp"
        )
    ) == []


def test_existing_manifest_is_not_overwritten(
    tmp_path: Path,
) -> None:
    run_directory, manifest = build_test_context(
        tmp_path
    )

    write_run_manifest(
        run_directory,
        manifest,
    )
    original_contents = (
        run_directory.manifest_path.read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(FileExistsError):
        write_run_manifest(
            run_directory,
            manifest,
        )

    assert (
        run_directory.manifest_path.read_text(
            encoding="utf-8"
        )
        == original_contents
    )


def test_manifest_identity_must_match_directory(
    tmp_path: Path,
) -> None:
    run_directory, manifest = build_test_context(
        tmp_path
    )

    mismatched_manifests = (
        manifest.model_copy(
            update={
                "run_id": OTHER_RUN_ID,
            }
        ),
        manifest.model_copy(
            update={
                "scenario_id": "another_scenario",
            }
        ),
        manifest.model_copy(
            update={
                "started_at": STARTED_AT
                + timedelta(seconds=1),
            }
        ),
    )

    for mismatched_manifest in mismatched_manifests:
        with pytest.raises(ValueError):
            write_run_manifest(
                run_directory,
                mismatched_manifest,
            )

    assert not run_directory.manifest_path.exists()