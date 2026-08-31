# tests for terminal invalid-precondition results

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import json
from pathlib import Path
from uuid import UUID

from uav_ci.domain.enums import (
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
from uav_ci.runtime import (
    build_invalid_precondition_result,
    create_run_directory,
    write_invalid_precondition_result,
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


def make_evidence() -> EvidenceRef:
    return EvidenceRef(
        source=EvidenceSource.HARNESS,
        clock_domain=ClockDomain.UTC,
        timestamp_us=int(
            FINISHED_AT.timestamp()
            * 1_000_000
        ),
        signal="environment.preflight.passed",
        artifact_path=Path(
            "evidence/preflight.json"
        ),
        description=(
            "Environment preflight recorded one "
            "or more failed checks."
        ),
    )


def test_failed_precondition_is_invalid() -> None:
    evidence = make_evidence()

    result = build_invalid_precondition_result(
        make_manifest(),
        assertion_id="environment_ready",
        message=(
            "Environment preflight did not pass."
        ),
        finished_at=FINISHED_AT,
        evidence=(evidence,),
    )

    assertion = result.assertions[0]

    assert result.status is ResultStatus.INVALID
    assert (
        assertion.outcome
        is CheckOutcome.FAILED
    )
    assert assertion.evidence == (evidence,)
    assert result.harness_error is None


def test_unproven_precondition_is_invalid() -> None:
    result = build_invalid_precondition_result(
        make_manifest(),
        assertion_id="vehicle_ready",
        message=(
            "Vehicle preconditions were not "
            "proven."
        ),
        finished_at=FINISHED_AT,
    )

    assertion = result.assertions[0]

    assert result.status is ResultStatus.INVALID
    assert (
        assertion.outcome
        is CheckOutcome.NOT_EVALUATED
    )
    assert assertion.evidence == ()
    assert result.harness_error is None


def test_invalid_result_is_published(
    tmp_path: Path,
) -> None:
    manifest = make_manifest()
    run_directory = create_run_directory(
        tmp_path / "runs",
        run_id=manifest.run_id,
        scenario_id=manifest.scenario_id,
        started_at=manifest.started_at,
    )

    write_invalid_precondition_result(
        run_directory,
        manifest,
        assertion_id="environment_ready",
        message=(
            "Environment preflight did not pass."
        ),
        finished_at=FINISHED_AT,
        evidence=(make_evidence(),),
    )

    payload = json.loads(
        run_directory.result_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "invalid"
    assert payload["harness_error"] is None
    assert (
        payload["assertions"][0]["layer"]
        == "precondition"
    )
    assert (
        payload["assertions"][0]["outcome"]
        == "failed"
    )