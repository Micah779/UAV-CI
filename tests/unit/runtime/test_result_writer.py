# tests for immutable run-result publication

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import json
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
    ClockDomain,
    EvidenceSource,
    ResultStatus,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.domain.result import (
    AssertionResult,
    RunResult,
)
from uav_ci.runtime import (
    create_run_directory,
    write_run_result,
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
    30,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)
FINISHED_AT = STARTED_AT + timedelta(minutes=2)

SCENARIO_HASH = "a" * 64
MISSION_HASH = "b" * 64
ENVIRONMENT_HASH = "c" * 64


def make_manifest() -> RunManifest:
    return RunManifest(
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        scenario_hash=SCENARIO_HASH,
        mission_file=Path(
            "missions/baseline.plan"
        ),
        mission_hash=MISSION_HASH,
        environment_profile="px4-gz-x500-v1",
        environment_hash=ENVIRONMENT_HASH,
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


def make_evidence(
    signal: str,
    artifact_path: str,
) -> EvidenceRef:
    return EvidenceRef(
        source=EvidenceSource.TELEMETRY,
        clock_domain=ClockDomain.HOST_MONOTONIC,
        timestamp_us=1_000_000,
        signal=signal,
        artifact_path=Path(artifact_path),
        description=(
            f"Observed {signal} during the run."
        ),
    )


def make_result() -> RunResult:
    return RunResult(
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        scenario_hash=SCENARIO_HASH,
        requires_activation=False,
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        assertions=(
            AssertionResult(
                assertion_id="vehicle_ready",
                layer=AssertionLayer.PRECONDITION,
                outcome=CheckOutcome.PASSED,
                message=(
                    "Vehicle preconditions passed."
                ),
                evidence=(
                    make_evidence(
                        "vehicle.preconditions",
                        (
                            "evidence/"
                            "vehicle_preconditions.json"
                        ),
                    ),
                ),
            ),
            AssertionResult(
                assertion_id="vehicle_landed",
                layer=AssertionLayer.OUTCOME,
                outcome=CheckOutcome.PASSED,
                message=(
                    "Vehicle landing was observed."
                ),
                evidence=(
                    make_evidence(
                        "vehicle.landed",
                        (
                            "evidence/"
                            "mission_execution.json"
                        ),
                    ),
                ),
            ),
        ),
    )


def make_run_directory(
    tmp_path: Path,
):
    return create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )


def test_result_is_written_with_computed_status(
    tmp_path: Path,
) -> None:
    run_directory = make_run_directory(
        tmp_path
    )
    manifest = make_manifest()
    result = make_result()

    result_path = write_run_result(
        run_directory,
        manifest,
        result,
    )

    payload = json.loads(
        result_path.read_text(
            encoding="utf-8"
        )
    )

    assert result_path == run_directory.result_path
    assert payload["status"] == "pass"
    assert result.status is ResultStatus.PASS

    # Status is computed output, so remove it before
    # reconstructing the input model.
    payload.pop("status")

    restored = RunResult.model_validate(payload)

    assert restored == result


def test_existing_result_is_not_overwritten(
    tmp_path: Path,
) -> None:
    run_directory = make_run_directory(
        tmp_path
    )
    manifest = make_manifest()
    result = make_result()

    write_run_result(
        run_directory,
        manifest,
        result,
    )
    original_contents = (
        run_directory.result_path.read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(FileExistsError):
        write_run_result(
            run_directory,
            manifest,
            result,
        )

    assert (
        run_directory.result_path.read_text(
            encoding="utf-8"
        )
        == original_contents
    )


def test_result_identity_must_match_manifest(
    tmp_path: Path,
) -> None:
    run_directory = make_run_directory(
        tmp_path
    )
    manifest = make_manifest()
    result = make_result()

    mismatched_results = (
        result.model_copy(
            update={"run_id": OTHER_RUN_ID}
        ),
        result.model_copy(
            update={"scenario_id": "other_scenario"}
        ),
        result.model_copy(
            update={"scenario_hash": "d" * 64}
        ),
        result.model_copy(
            update={"requires_activation": True}
        ),
        result.model_copy(
            update={
                "started_at": (
                    STARTED_AT
                    + timedelta(seconds=1)
                )
            }
        ),
    )

    for mismatched_result in mismatched_results:
        with pytest.raises(ValueError):
            write_run_result(
                run_directory,
                manifest,
                mismatched_result,
            )

    assert not run_directory.result_path.exists()


def test_manifest_identity_must_match_directory(
    tmp_path: Path,
) -> None:
    run_directory = make_run_directory(
        tmp_path
    )
    manifest = make_manifest().model_copy(
        update={
            "scenario_id": "other_scenario",
        }
    )

    with pytest.raises(
        ValueError,
        match="manifest scenario_id",
    ):
        write_run_result(
            run_directory,
            manifest,
            make_result(),
        )

    assert not run_directory.result_path.exists()