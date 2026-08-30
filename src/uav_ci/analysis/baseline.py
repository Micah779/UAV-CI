# evaluate the constrained baseline assurance scenario

from datetime import datetime, timedelta
from pathlib import Path

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
from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.vehicle import (
    MissionExecutionResult,
    VehiclePreconditionResult,
)


class BaselineEvaluationError(RuntimeError):
    # baseline scenario cannot be evaluated safely
    pass


def _utc_timestamp_us(
    value: datetime,
) -> int:
    if value.utcoffset() != timedelta(0):
        raise BaselineEvaluationError(
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


def _validate_baseline_contract(
    scenario: ScenarioSpec,
    manifest: RunManifest,
) -> None:
    if (
        scenario.scenario_id
        != manifest.scenario_id
    ):
        raise BaselineEvaluationError(
            "scenario does not match run manifest"
        )

    if (
        scenario.requires_activation
        or manifest.requires_activation
    ):
        raise BaselineEvaluationError(
            "baseline evaluation cannot require "
            "fault activation"
        )

    if len(scenario.assertions) != 1:
        raise BaselineEvaluationError(
            "baseline scenario must declare exactly "
            "one outcome assertion"
        )

    assertion = scenario.assertions[0]

    supported = all(
        (
            assertion.assertion_id
            == "vehicle_landed",
            assertion.layer
            is AssertionLayer.OUTCOME,
            assertion.source
            is EvidenceSource.ULOG,
            assertion.signal
            == "vehicle_land_detected.landed",
            assertion.operator
            is ComparisonOperator.EQUAL,
            assertion.expected is True,
        )
    )

    if not supported:
        raise BaselineEvaluationError(
            "baseline assertion contract is not "
            "supported"
        )


def evaluate_baseline(
    scenario: ScenarioSpec,
    manifest: RunManifest,
    *,
    preconditions: VehiclePreconditionResult,
    mission: MissionExecutionResult,
    land_detection: LandDetectionSummary,
    finished_at: datetime,
) -> RunResult:
    # build the baseline result from retained evidence

    _validate_baseline_contract(
        scenario,
        manifest,
    )

    finished_timestamp_us = (
        _utc_timestamp_us(finished_at)
    )
    precondition_timestamp_us = (
        _utc_timestamp_us(
            preconditions.observed_at
        )
    )

    preconditions_passed = (
        preconditions.passed
    )
    airborne_passed = all(
        (
            mission.airborne_observed,
            land_detection.airborne_observed,
            (
                land_detection
                .first_airborne_timestamp_us
                is not None
            ),
        )
    )
    landed_passed = all(
        (
            mission.landed_observed,
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
    disarmed_passed = (
        mission.disarmed_observed
    )

    precondition_evidence = EvidenceRef(
        source=EvidenceSource.TELEMETRY,
        clock_domain=ClockDomain.UTC,
        timestamp_us=(
            precondition_timestamp_us
        ),
        signal="vehicle.preconditions.passed",
        artifact_path=Path(
            "evidence/vehicle_preconditions.json"
        ),
        description=(
            "MAVSDK telemetry recorded the "
            "preflight vehicle state."
        ),
    )

    airborne_ulog_evidence = EvidenceRef(
        source=EvidenceSource.ULOG,
        clock_domain=ClockDomain.PX4_BOOT,
        timestamp_us=(
            land_detection
            .first_airborne_timestamp_us
            if (
                land_detection
                .first_airborne_timestamp_us
                is not None
            )
            else land_detection.last_timestamp_us
        ),
        signal="vehicle_land_detected.landed",
        artifact_path=Path(
            "logs/flight.ulg"
        ),
        description=(
            "PX4 ULog land detection was used "
            "to determine whether the vehicle "
            "became airborne."
        ),
    )

    mission_airborne_evidence = EvidenceRef(
        source=EvidenceSource.HARNESS,
        clock_domain=ClockDomain.UTC,
        timestamp_us=finished_timestamp_us,
        signal=(
            "mission_execution.airborne_observed"
        ),
        artifact_path=Path(
            "evidence/mission_execution.json"
        ),
        description=(
            "The live mission executor required "
            "airborne telemetry before completion."
        ),
    )

    landed_ulog_evidence = EvidenceRef(
        source=EvidenceSource.ULOG,
        clock_domain=ClockDomain.PX4_BOOT,
        timestamp_us=(
            land_detection.landing_timestamp_us
            if (
                land_detection
                .landing_timestamp_us
                is not None
            )
            else land_detection.last_timestamp_us
        ),
        signal="vehicle_land_detected.landed",
        artifact_path=Path(
            "logs/flight.ulg"
        ),
        description=(
            "PX4 ULog recorded the final landing "
            "state and landing transition."
        ),
    )

    mission_landed_evidence = EvidenceRef(
        source=EvidenceSource.HARNESS,
        clock_domain=ClockDomain.UTC,
        timestamp_us=finished_timestamp_us,
        signal=(
            "mission_execution.landed_observed"
        ),
        artifact_path=Path(
            "evidence/mission_execution.json"
        ),
        description=(
            "The live mission executor observed "
            "the vehicle on the ground."
        ),
    )

    disarmed_evidence = EvidenceRef(
        source=EvidenceSource.HARNESS,
        clock_domain=ClockDomain.UTC,
        timestamp_us=finished_timestamp_us,
        signal=(
            "mission_execution.disarmed_observed"
        ),
        artifact_path=Path(
            "evidence/mission_execution.json"
        ),
        description=(
            "The live mission executor observed "
            "the vehicle disarmed after landing."
        ),
    )

    assertions = (
        AssertionResult(
            assertion_id="vehicle_ready",
            layer=AssertionLayer.PRECONDITION,
            outcome=_outcome(
                preconditions_passed
            ),
            message=(
                "Vehicle preconditions passed."
                if preconditions_passed
                else (
                    "Vehicle preconditions did "
                    "not pass."
                )
            ),
            evidence=(
                precondition_evidence,
            ),
        ),
        AssertionResult(
            assertion_id=(
                "mission_became_airborne"
            ),
            layer=AssertionLayer.RESPONSE,
            outcome=_outcome(
                airborne_passed
            ),
            message=(
                "The vehicle became airborne."
                if airborne_passed
                else (
                    "Airborne state was not "
                    "proven."
                )
            ),
            evidence=(
                airborne_ulog_evidence,
                mission_airborne_evidence,
            ),
        ),
        AssertionResult(
            assertion_id="vehicle_landed",
            layer=AssertionLayer.OUTCOME,
            outcome=_outcome(
                landed_passed
            ),
            message=(
                "The vehicle completed a landing "
                "transition."
                if landed_passed
                else (
                    "A final landing transition "
                    "was not proven."
                )
            ),
            evidence=(
                landed_ulog_evidence,
                mission_landed_evidence,
            ),
        ),
        AssertionResult(
            assertion_id="vehicle_disarmed",
            layer=AssertionLayer.OUTCOME,
            outcome=_outcome(
                disarmed_passed
            ),
            message=(
                "The vehicle disarmed after "
                "landing."
                if disarmed_passed
                else (
                    "Post-flight disarming was "
                    "not proven."
                )
            ),
            evidence=(
                disarmed_evidence,
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