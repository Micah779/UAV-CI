# tests for baseline assurance evaluation

from dataclasses import replace
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.analysis import (
    BaselineEvaluationError,
    LandDetectionSummary,
    evaluate_baseline,
)
from uav_ci.domain.enums import (
    CheckOutcome,
    ResultStatus,
)
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.scenario import load_scenario
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionResult,
)


PROJECT_ROOT = Path(__file__).parents[3]
BASELINE_SCENARIO = (
    PROJECT_ROOT
    / "scenarios"
    / "baseline.yaml"
)

RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
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
FINISHED_AT = (
    STARTED_AT + timedelta(minutes=2)
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


def make_preconditions() -> VehiclePreconditionResult:
    return VehiclePreconditionResult(
        observed_at=(
            STARTED_AT
            + timedelta(seconds=10)
        ),
        elapsed_s=1.0,
        gyrometer_calibration_ok=True,
        accelerometer_calibration_ok=True,
        magnetometer_calibration_ok=True,
        local_position_ok=True,
        global_position_ok=True,
        home_position_ok=True,
        armable=True,
        armed=False,
        landed_state="on_ground",
    )


def make_mission() -> MissionExecutionResult:
    return MissionExecutionResult(
        mission_item_count=4,
        final_current=4,
        final_total=4,
        armed_observed=True,
        airborne_observed=True,
        landed_observed=True,
        disarmed_observed=True,
        elapsed_s=120.0,
    )


def make_land_detection() -> LandDetectionSummary:
    return LandDetectionSummary(
        topic="vehicle_land_detected",
        instance=0,
        sample_count=100,
        first_timestamp_us=1_000_000,
        last_timestamp_us=121_000_000,
        initial_landed=True,
        airborne_observed=True,
        first_airborne_timestamp_us=(
            5_000_000
        ),
        final_landed=True,
        landing_transition_observed=True,
        landing_timestamp_us=120_000_000,
    )


def evaluate(
    *,
    preconditions=None,
    mission=None,
    land_detection=None,
):
    scenario = load_scenario(
        BASELINE_SCENARIO
    ).scenario

    return evaluate_baseline(
        scenario,
        make_manifest(),
        preconditions=(
            preconditions
            if preconditions is not None
            else make_preconditions()
        ),
        mission=(
            mission
            if mission is not None
            else make_mission()
        ),
        land_detection=(
            land_detection
            if land_detection is not None
            else make_land_detection()
        ),
        finished_at=FINISHED_AT,
    )


def test_complete_baseline_evidence_passes() -> None:
    result = evaluate()

    assert result.status is ResultStatus.PASS
    assert tuple(
        assertion.assertion_id
        for assertion in result.assertions
    ) == (
        "vehicle_ready",
        "mission_became_airborne",
        "vehicle_landed",
        "vehicle_disarmed",
    )
    assert all(
        assertion.outcome
        is CheckOutcome.PASSED
        for assertion in result.assertions
    )
    assert (
        result.assertions[2]
        .evidence[0]
        .artifact_path
        == Path("logs/flight.ulg")
    )


def test_missing_airborne_proof_fails() -> None:
    land_detection = replace(
        make_land_detection(),
        airborne_observed=False,
        first_airborne_timestamp_us=None,
    )

    result = evaluate(
        land_detection=land_detection
    )

    assert result.status is ResultStatus.FAIL
    assert (
        result.assertions[1].outcome
        is CheckOutcome.FAILED
    )


def test_missing_landing_proof_fails() -> None:
    land_detection = replace(
        make_land_detection(),
        final_landed=False,
        landing_transition_observed=False,
        landing_timestamp_us=None,
    )

    result = evaluate(
        land_detection=land_detection
    )

    assert result.status is ResultStatus.FAIL
    assert (
        result.assertions[2].outcome
        is CheckOutcome.FAILED
    )


def test_failed_preconditions_are_invalid() -> None:
    preconditions = (
        make_preconditions().model_copy(
            update={
                "armable": False,
            }
        )
    )

    result = evaluate(
        preconditions=preconditions
    )

    assert result.status is ResultStatus.INVALID
    assert (
        result.assertions[0].outcome
        is CheckOutcome.FAILED
    )


def test_missing_disarm_proof_fails() -> None:
    mission = replace(
        make_mission(),
        disarmed_observed=False,
    )

    result = evaluate(
        mission=mission
    )

    assert result.status is ResultStatus.FAIL
    assert (
        result.assertions[3].outcome
        is CheckOutcome.FAILED
    )


def test_unsupported_baseline_contract_is_rejected() -> None:
    scenario = load_scenario(
        BASELINE_SCENARIO
    ).scenario.model_copy(
        update={
            "assertions": (),
        }
    )

    with pytest.raises(
        BaselineEvaluationError,
        match="exactly one",
    ):
        evaluate_baseline(
            scenario,
            make_manifest(),
            preconditions=make_preconditions(),
            mission=make_mission(),
            land_detection=(
                make_land_detection()
            ),
            finished_at=FINISHED_AT,
        )