# build and publish terminal invalid-precondition results

from datetime import datetime

from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.manifest import RunManifest
from uav_ci.domain.result import (
    AssertionResult,
    RunResult,
)
from uav_ci.runtime.result_writer import (
    write_run_result,
)
from uav_ci.runtime.run_directory import (
    RunDirectory,
)


def build_invalid_precondition_result(
    manifest: RunManifest,
    *,
    assertion_id: str,
    message: str,
    finished_at: datetime,
    evidence: tuple[EvidenceRef, ...] = (),
) -> RunResult:
    # represent a failed or unproven precondition

    outcome = (
        CheckOutcome.FAILED
        if evidence
        else CheckOutcome.NOT_EVALUATED
    )

    assertion = AssertionResult(
        assertion_id=assertion_id,
        layer=AssertionLayer.PRECONDITION,
        outcome=outcome,
        message=message,
        evidence=evidence,
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
        assertions=(assertion,),
    )


def write_invalid_precondition_result(
    run_directory: RunDirectory,
    manifest: RunManifest,
    *,
    assertion_id: str,
    message: str,
    finished_at: datetime,
    evidence: tuple[EvidenceRef, ...] = (),
) -> RunResult:
    # build and exclusively publish an INVALID result

    result = build_invalid_precondition_result(
        manifest,
        assertion_id=assertion_id,
        message=message,
        finished_at=finished_at,
        evidence=evidence,
    )

    write_run_result(
        run_directory,
        manifest,
        result,
    )

    return result