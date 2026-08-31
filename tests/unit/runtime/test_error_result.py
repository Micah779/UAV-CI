# tests for terminal harness-error results

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import json
from pathlib import Path
from uuid import UUID

from uav_ci.domain.enums import ResultStatus
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.runtime import (
    build_harness_error_result,
    create_run_directory,
    describe_harness_error,
    write_harness_error_result,
)


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
STARTED_AT = datetime(
    2026,
    8,
    31,
    12,
    0,
    tzinfo=timezone.utc,
)
FINISHED_AT = (
    STARTED_AT + timedelta(seconds=30)
)


def make_manifest() -> RunManifest:
    return RunManifest(
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        scenario_hash="a" * 64,
        mission_file=Path(
            "missions/baseline.plan"
        ),
        mission_hash="b" * 64,
        environment_profile="px4-gz-x500-v1",
        environment_hash="c" * 64,
        requires_activation=False,
        repetition_index=1,
        repetition_count=1,
        seed=42,
        started_at=STARTED_AT,
        harness=HarnessProvenance(
            uav_ci_version="0.1.0",
            python_version="3.14.7",
            platform="test-platform",
        ),
    )


def test_error_description_preserves_notes() -> None:
    error = RuntimeError(
        "mission execution failed"
    )
    error.add_note(
        "ULog capture also failed"
    )

    description = describe_harness_error(
        error
    )

    assert description == (
        "RuntimeError: mission execution failed\n"
        "note: ULog capture also failed"
    )


def test_harness_error_builds_error_result() -> None:
    result = build_harness_error_result(
        make_manifest(),
        error=RuntimeError(
            "post-flight analysis failed"
        ),
        finished_at=FINISHED_AT,
    )

    assert result.status is ResultStatus.ERROR
    assert result.run_id == RUN_ID
    assert result.finished_at == FINISHED_AT
    assert result.assertions == ()
    assert result.harness_error == (
        "RuntimeError: "
        "post-flight analysis failed"
    )


def test_harness_error_result_is_published(
    tmp_path: Path,
) -> None:
    manifest = make_manifest()
    run_directory = create_run_directory(
        tmp_path / "runs",
        run_id=manifest.run_id,
        scenario_id=manifest.scenario_id,
        started_at=manifest.started_at,
    )

    result = write_harness_error_result(
        run_directory,
        manifest,
        error=RuntimeError(
            "ULog analysis failed"
        ),
        finished_at=FINISHED_AT,
    )

    payload = json.loads(
        run_directory.result_path.read_text(
            encoding="utf-8"
        )
    )

    assert result.status is ResultStatus.ERROR
    assert payload["status"] == "error"
    assert payload["harness_error"] == (
        "RuntimeError: ULog analysis failed"
    )
    assert payload["assertions"] == []