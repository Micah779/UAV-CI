# build and publish INVALID results for unproven fault activation

from datetime import datetime, timedelta
from pathlib import Path

from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
    ClockDomain,
    EvidenceSource,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.manifest import (
    RunManifest,
)
from uav_ci.domain.result import (
    AssertionResult,
    RunResult,
)
from uav_ci.faults.controller import (
    FaultActivationResult,
)
from uav_ci.runtime.result_writer import (
    write_run_result,
)
from uav_ci.runtime.run_directory import (
    RunDirectory,
)
from uav_ci.vehicle import (
    VehiclePreconditionResult,
)


def build_invalid_activation_result(
    manifest: RunManifest,
    *,
    assertion_id: str,
    preconditions: VehiclePreconditionResult,
    activation: FaultActivationResult,
    finished_at: datetime,
) -> RunResult:
    if not manifest.requires_activation:
        raise ValueError(
            "manifest does not require "
            "fault activation"
        )

    if activation.activated:
        raise ValueError(
            "proven activation is not "
            "an invalid run"
        )

    if not activation.evidence:
        raise ValueError(
            "unproven activation requires "
            "assessment evidence"
        )

    if not preconditions.passed:
        raise ValueError(
            "activation invalid result requires "
            "passed preconditions"
        )

    if (
        preconditions
        .observed_at
        .utcoffset()
        != timedelta(0)
    ):
        raise ValueError(
            "precondition evidence timestamp "
            "must use UTC"
        )

    precondition_evidence = EvidenceRef(
        source=EvidenceSource.TELEMETRY,
        clock_domain=ClockDomain.UTC,
        timestamp_us=int(
            preconditions
            .observed_at
            .timestamp()
            * 1_000_000
        ),
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

    return RunResult(
        run_id=manifest.run_id,
        scenario_id=manifest.scenario_id,
        scenario_hash=manifest.scenario_hash,
        requires_activation=True,
        started_at=manifest.started_at,
        finished_at=finished_at,
        assertions=(
            AssertionResult(
                assertion_id="vehicle_ready",
                layer=(
                    AssertionLayer
                    .PRECONDITION
                ),
                outcome=CheckOutcome.PASSED,
                message=(
                    "Vehicle preconditions passed."
                ),
                evidence=(
                    precondition_evidence,
                ),
            ),
            AssertionResult(
                assertion_id=assertion_id,
                layer=(
                    AssertionLayer.ACTIVATION
                ),
                outcome=CheckOutcome.FAILED,
                message=(
                    "Fault activation was not "
                    "proven; response assertions "
                    "were not evaluated."
                ),
                evidence=activation.evidence,
            ),
        ),
    )


def write_invalid_activation_result(
    run_directory: RunDirectory,
    manifest: RunManifest,
    **options,
) -> RunResult:
    result = (
        build_invalid_activation_result(
            manifest,
            **options,
        )
    )

    write_run_result(
        run_directory,
        manifest,
        result,
    )

    return result