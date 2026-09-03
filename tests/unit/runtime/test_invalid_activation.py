# unproven activation is INVALID before response evaluation

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.domain.enums import (
    AssertionLayer,
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
from uav_ci.runtime.invalid_activation import (
    build_invalid_activation_result,
    write_invalid_activation_result,
)
from uav_ci.runtime.run_directory import (
    create_run_directory,
)
from uav_ci.vehicle import (
    VehiclePreconditionResult,
)


START = datetime(
    2026,
    9,
    3,
    tzinfo=timezone.utc,
)
RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)


def manifest(required=True):
    return RunManifest(
        run_id=RUN_ID,
        scenario_id="wind_tracking",
        scenario_hash="a" * 64,
        mission_file=Path(
            "missions/baseline.plan"
        ),
        mission_hash="b" * 64,
        environment_profile="px4-gz-x500-v1",
        environment_hash="c" * 64,
        requires_activation=required,
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


def preconditions(passed=True):
    return VehiclePreconditionResult(
        observed_at=(
            START + timedelta(seconds=10)
        ),
        elapsed_s=1,
        gyrometer_calibration_ok=passed,
        accelerometer_calibration_ok=True,
        magnetometer_calibration_ok=True,
        local_position_ok=True,
        global_position_ok=True,
        home_position_ok=True,
        armable=True,
        armed=False,
        landed_state="on_ground",
    )


def activation(
    proven=False,
    evidence=True,
):
    refs = ()

    if evidence:
        refs = (
            EvidenceRef(
                source="harness",
                clock_domain="host_monotonic",
                timestamp_us=100,
                signal=(
                    "wind_activation.assessment"
                ),
                artifact_path=Path(
                    "evidence/wind/activation.json"
                ),
                description=(
                    "synthetic assessment"
                ),
            ),
        )

    return FaultActivationResult(
        fault_type="wind",
        activated=proven,
        evidence=refs,
    )


def build(**changes):
    values = dict(
        manifest=manifest(),
        assertion_id="wind_reached_vehicle",
        preconditions=preconditions(),
        activation=activation(),
        finished_at=(
            START + timedelta(minutes=2)
        ),
    )
    values.update(changes)

    return build_invalid_activation_result(
        **values
    )


def test_unproven_activation_is_invalid_without_behavior_results():
    result = build()

    assert (
        result.status
        is ResultStatus.INVALID
    )
    assert [
        item.layer
        for item in result.assertions
    ] == [
        AssertionLayer.PRECONDITION,
        AssertionLayer.ACTIVATION,
    ]
    assert (
        result.assertions[0].outcome
        is CheckOutcome.PASSED
    )
    assert (
        result.assertions[1].outcome
        is CheckOutcome.FAILED
    )
    assert not any(
        item.layer
        in {
            AssertionLayer.RESPONSE,
            AssertionLayer.OUTCOME,
        }
        for item in result.assertions
    )


@pytest.mark.parametrize(
    "changes",
    [
        {
            "manifest": manifest(False),
        },
        {
            "activation": activation(True),
        },
        {
            "activation": activation(
                False,
                False,
            ),
        },
        {
            "preconditions": preconditions(False),
        },
    ],
)
def test_invalid_builder_rejects_inconsistent_context(
    changes,
):
    with pytest.raises(ValueError):
        build(**changes)


def test_result_is_published_exclusively(
    tmp_path,
):
    directory = create_run_directory(
        tmp_path,
        run_id=RUN_ID,
        scenario_id="wind_tracking",
        started_at=START,
    )

    result = write_invalid_activation_result(
        directory,
        manifest(),
        assertion_id="wind_reached_vehicle",
        preconditions=preconditions(),
        activation=activation(),
        finished_at=(
            START + timedelta(minutes=2)
        ),
    )

    assert (
        result.status
        is ResultStatus.INVALID
    )
    assert directory.result_path.is_file()

    with pytest.raises(FileExistsError):
        write_invalid_activation_result(
            directory,
            manifest(),
            assertion_id=(
                "wind_reached_vehicle"
            ),
            preconditions=preconditions(),
            activation=activation(),
            finished_at=(
                START + timedelta(minutes=2)
            ),
        )