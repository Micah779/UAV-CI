# evaluate the constrained wind assurance scenario

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from uav_ci.analysis.ulog import (
    LandDetectionSummary,
)
from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
    ClockDomain,
    ComparisonOperator,
    EvidenceSource,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.manifest import RunManifest
from uav_ci.domain.result import (
    AssertionResult,
    RunResult,
)
from uav_ci.domain.scenario import (
    ScenarioSpec,
    WindStimulusSpec,
)
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionResult,
)

if TYPE_CHECKING:
    from uav_ci.faults.controller import (
        FaultActivationResult,
    )


class WindEvaluationError(RuntimeError):
    pass


def _utc_timestamp_us(
    value: datetime,
) -> int:
    if value.utcoffset() != timedelta(0):
        raise WindEvaluationError(
            "evidence timestamps must use UTC"
        )

    return int(
        value.timestamp() * 1_000_000
    )


def _outcome(
    passed: bool,
) -> CheckOutcome:
    return (
        CheckOutcome.PASSED
        if passed
        else CheckOutcome.FAILED
    )


def validate_wind_contract(
    scenario: ScenarioSpec,
    manifest: RunManifest,
) -> None:
    if (
        scenario.scenario_id
        != manifest.scenario_id
    ):
        raise WindEvaluationError(
            "scenario does not match run manifest"
        )

    if not isinstance(
        scenario.stimulus,
        WindStimulusSpec,
    ):
        raise WindEvaluationError(
            "wind evaluation requires "
            "a wind stimulus"
        )

    if not manifest.requires_activation:
        raise WindEvaluationError(
            "wind manifest must require activation"
        )

    if scenario.parameters.overrides:
        raise WindEvaluationError(
            "wind flights do not support "
            "parameter overrides yet"
        )

    if len(scenario.assertions) != 2:
        raise WindEvaluationError(
            "wind scenario must declare "
            "two assertions"
        )

    by_id = {
        item.assertion_id: item
        for item in scenario.assertions
    }

    if set(by_id) != {
        "wind_reached_vehicle",
        "vehicle_landed",
    }:
        raise WindEvaluationError(
            "wind assertion contract "
            "is not supported"
        )

    wind = by_id[
        "wind_reached_vehicle"
    ]
    landed = by_id[
        "vehicle_landed"
    ]

    supported = all(
        (
            wind.layer
            is AssertionLayer.ACTIVATION,
            wind.source
            is EvidenceSource.SIMULATOR,
            wind.signal
            == "gazebo.wind.speed_m_s",
            wind.operator
            is (
                ComparisonOperator
                .GREATER_THAN_OR_EQUAL
            ),
            wind.expected
            == (
                scenario
                .stimulus
                .minimum_proven_speed_m_s
            ),
            wind.within_s
            == (
                scenario
                .stimulus
                .activation_timeout_s
            ),
            wind.tolerance is None,
            landed.layer
            is AssertionLayer.OUTCOME,
            landed.source
            is EvidenceSource.ULOG,
            landed.signal
            == "vehicle_land_detected.landed",
            landed.operator
            is ComparisonOperator.EQUAL,
            landed.expected is True,
            landed.within_s is None,
            landed.tolerance is None,
        )
    )

    if not supported:
        raise WindEvaluationError(
            "wind assertion contract "
            "is not supported"
        )


def evaluate_wind(
    scenario: ScenarioSpec,
    manifest: RunManifest,
    *,
    preconditions: VehiclePreconditionResult,
    activation: "FaultActivationResult",
    mission: MissionExecutionResult,
    land_detection: LandDetectionSummary,
    finished_at: datetime,
) -> RunResult:
    validate_wind_contract(
        scenario,
        manifest,
    )

    if (
        activation.fault_type != "wind"
        or not activation.activated
    ):
        raise WindEvaluationError(
            "wind activation must be "
            "proven first"
        )

    if not activation.evidence:
        raise WindEvaluationError(
            "wind activation evidence is missing"
        )

    finished_us = _utc_timestamp_us(
        finished_at
    )
    precondition_us = _utc_timestamp_us(
        preconditions.observed_at
    )

    landed_passed = all(
        (
            mission.landed_observed,
            land_detection.airborne_observed,
            land_detection.final_landed,
            (
                land_detection
                .landing_transition_observed
            ),
            (
                land_detection
                .landing_timestamp_us
                is not None
            ),
        )
    )

    precondition_evidence = EvidenceRef(
        source=EvidenceSource.TELEMETRY,
        clock_domain=ClockDomain.UTC,
        timestamp_us=precondition_us,
        signal=(
            "vehicle.preconditions.passed"
        ),
        artifact_path=Path(
            "evidence/vehicle_preconditions.json"
        ),
        description=(
            "MAVSDK telemetry recorded the "
            "preflight vehicle state."
        ),
    )

    landed_ulog_evidence = EvidenceRef(
        source=EvidenceSource.ULOG,
        clock_domain=ClockDomain.PX4_BOOT,
        timestamp_us=(
            land_detection
            .landing_timestamp_us
            if (
                land_detection
                .landing_timestamp_us
                is not None
            )
            else (
                land_detection
                .last_timestamp_us
            )
        ),
        signal=(
            "vehicle_land_detected.landed"
        ),
        artifact_path=Path(
            "logs/flight.ulg"
        ),
        description=(
            "PX4 ULog recorded the airborne "
            "state, final landing state, and "
            "landing transition."
        ),
    )

    mission_evidence = EvidenceRef(
        source=EvidenceSource.HARNESS,
        clock_domain=ClockDomain.UTC,
        timestamp_us=finished_us,
        signal=(
            "mission_execution.landed_observed"
        ),
        artifact_path=Path(
            "evidence/mission_execution.json"
        ),
        description=(
            "The live mission executor observed "
            "landing and disarming."
        ),
    )

    assertions = (
        AssertionResult(
            assertion_id="vehicle_ready",
            layer=AssertionLayer.PRECONDITION,
            outcome=_outcome(
                preconditions.passed
            ),
            message=(
                "Vehicle preconditions passed."
                if preconditions.passed
                else (
                    "Vehicle preconditions "
                    "did not pass."
                )
            ),
            evidence=(
                precondition_evidence,
            ),
        ),
        AssertionResult(
            assertion_id=(
                "wind_reached_vehicle"
            ),
            layer=AssertionLayer.ACTIVATION,
            outcome=CheckOutcome.PASSED,
            message=(
                "The configured Gazebo wind "
                "activation was proven."
            ),
            evidence=activation.evidence,
        ),
        AssertionResult(
            assertion_id="vehicle_landed",
            layer=AssertionLayer.OUTCOME,
            outcome=_outcome(
                landed_passed
            ),
            message=(
                "The wind-exposed vehicle "
                "completed a landing transition."
                if landed_passed
                else (
                    "Landing after proven wind "
                    "activation was not proven."
                )
            ),
            evidence=(
                landed_ulog_evidence,
                mission_evidence,
            ),
        ),
    )

    return RunResult(
        run_id=manifest.run_id,
        scenario_id=manifest.scenario_id,
        scenario_hash=manifest.scenario_hash,
        requires_activation=(
            manifest.requires_activation
        ),
        started_at=manifest.started_at,
        finished_at=finished_at,
        assertions=assertions,
    )