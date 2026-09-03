# wind-result evaluation uses synthetic evidence models

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.analysis.ulog import LandDetectionSummary
from uav_ci.analysis.wind import (
    WindEvaluationError,
    evaluate_wind,
)
from uav_ci.domain.enums import (
    CheckOutcome,
    ResultStatus,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.faults.controller import (
    FaultActivationResult,
)
from uav_ci.scenario import load_scenario
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionResult,
)


ROOT = Path(__file__).parents[3]
START = datetime(
    2026,
    9,
    3,
    tzinfo=timezone.utc,
)
FINISH = START + timedelta(minutes=2)


def scenario():
    return load_scenario(
        ROOT / "scenarios/wind.yaml"
    ).scenario


def manifest(**changes):
    values = dict(
        run_id=UUID(
            "12345678-1234-5678-1234-567812345678"
        ),
        scenario_id="wind_tracking",
        scenario_hash="a" * 64,
        mission_file=Path(
            "missions/baseline.plan"
        ),
        mission_hash="b" * 64,
        environment_profile="px4-gz-x500-v1",
        environment_hash="c" * 64,
        requires_activation=True,
        repetition_index=1,
        repetition_count=1,
        seed=42,
        started_at=START,
        harness=HarnessProvenance(
            uav_ci_version="0.1.0",
            python_version="3.14.7",
            platform="test",
        ),
    )
    values.update(changes)

    return RunManifest(**values)


def preconditions():
    return VehiclePreconditionResult(
        observed_at=(
            START + timedelta(seconds=10)
        ),
        elapsed_s=1,
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


def mission():
    return MissionExecutionResult(
        mission_item_count=4,
        final_current=4,
        final_total=4,
        armed_observed=True,
        airborne_observed=True,
        landed_observed=True,
        disarmed_observed=True,
        elapsed_s=120,
    )


def land():
    return LandDetectionSummary(
        topic="vehicle_land_detected",
        instance=0,
        sample_count=100,
        first_timestamp_us=1_000_000,
        last_timestamp_us=121_000_000,
        initial_landed=True,
        airborne_observed=True,
        first_airborne_timestamp_us=5_000_000,
        final_landed=True,
        landing_transition_observed=True,
        landing_timestamp_us=120_000_000,
    )


def activation(proven=True):
    evidence = EvidenceRef(
        source="harness",
        clock_domain="host_monotonic",
        timestamp_us=100_000_000,
        signal="wind_activation.assessment",
        artifact_path=Path(
            "evidence/wind/activation.json"
        ),
        description="synthetic wind assessment",
    )

    return FaultActivationResult(
        fault_type="wind",
        activated=proven,
        evidence=(evidence,),
    )


def evaluate(**changes):
    values = dict(
        scenario=scenario(),
        manifest=manifest(),
        preconditions=preconditions(),
        activation=activation(),
        mission=mission(),
        land_detection=land(),
        finished_at=FINISH,
    )
    values.update(changes)

    return evaluate_wind(**values)


def test_proven_wind_and_landing_pass():
    result = evaluate()

    assert result.status is ResultStatus.PASS
    assert [
        item.assertion_id
        for item in result.assertions
    ] == [
        "vehicle_ready",
        "wind_reached_vehicle",
        "vehicle_landed",
    ]
    assert all(
        item.outcome is CheckOutcome.PASSED
        for item in result.assertions
    )
    assert (
        result.assertions[1].evidence
        == activation().evidence
    )


def test_failed_landing_after_proven_activation_is_fail():
    summary = replace(
        land(),
        final_landed=False,
        landing_transition_observed=False,
        landing_timestamp_us=None,
    )

    result = evaluate(
        land_detection=summary
    )

    assert result.status is ResultStatus.FAIL
    assert (
        result.assertions[2].outcome
        is CheckOutcome.FAILED
    )


@pytest.mark.parametrize(
    "changes",
    [
        {
            "activation": activation(False),
        },
        {
            "manifest": manifest(
                requires_activation=False
            ),
        },
        {
            "manifest": manifest(
                scenario_id="different"
            ),
        },
    ],
)
def test_unsafe_evaluation_context_is_rejected(
    changes,
):
    with pytest.raises(WindEvaluationError):
        evaluate(**changes)


def test_baseline_scenario_is_rejected():
    baseline = load_scenario(
        ROOT / "scenarios/baseline.yaml"
    ).scenario

    with pytest.raises(
        WindEvaluationError,
        match="wind stimulus",
    ):
        evaluate(
            scenario=baseline,
            manifest=manifest(
                scenario_id="baseline_mission"
            ),
        )


def test_non_utc_finish_is_rejected():
    local = FINISH.astimezone(
        timezone(timedelta(hours=-5))
    )

    with pytest.raises(
        WindEvaluationError,
        match="UTC",
    ):
        evaluate(finished_at=local)


def test_contract_changes_are_rejected():
    spec = scenario()
    changed = spec.model_copy(
        update={
            "assertions": spec.assertions[:1],
        }
    )

    with pytest.raises(
        WindEvaluationError,
        match="two assertions",
    ):
        evaluate(scenario=changed)