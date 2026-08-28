# tests most important status rules independently of PX4

from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
    ClockDomain,
    EvidenceSource,
    ResultStatus,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.result import AssertionResult, classify_run


def make_evidence() -> EvidenceRef:
    return EvidenceRef(
        source=EvidenceSource.TELEMETRY,
        clock_domain=ClockDomain.PX4_BOOT,
        timestamp_us=18_420_000,
        signal="test.signal",
        artifact_path="telemetry/events.jsonl",
        description="Evidence recorded for classifier testing.",
    )


def make_assertion(
    assertion_id: str,
    layer: AssertionLayer,
    outcome: CheckOutcome,
) -> AssertionResult:
    evidence: tuple[EvidenceRef, ...] = ()

    if outcome in {
        CheckOutcome.PASSED,
        CheckOutcome.FAILED,
    }:
        evidence = (make_evidence(),)

    return AssertionResult(
        assertion_id=assertion_id,
        layer=layer,
        outcome=outcome,
        message=f"{assertion_id} produced {outcome.value}.",
        evidence=evidence,
    )


def passing_fault_results() -> list[AssertionResult]:
    return [
        make_assertion(
            "vehicle_ready",
            AssertionLayer.PRECONDITION,
            CheckOutcome.PASSED,
        ),
        make_assertion(
            "gnss_updates_stopped",
            AssertionLayer.ACTIVATION,
            CheckOutcome.PASSED,
        ),
        make_assertion(
            "failsafe_selected",
            AssertionLayer.RESPONSE,
            CheckOutcome.PASSED,
        ),
        make_assertion(
            "vehicle_landed",
            AssertionLayer.OUTCOME,
            CheckOutcome.PASSED,
        ),
    ]


def test_harness_error_has_highest_precedence() -> None:
    status = classify_run(
        passing_fault_results(),
        requires_activation=True,
        harness_error=True,
        unsupported_environment=True,
    )

    assert status is ResultStatus.ERROR


def test_unsupported_environment_is_skipped() -> None:
    status = classify_run(
        [],
        requires_activation=True,
        unsupported_environment=True,
    )

    assert status is ResultStatus.SKIPPED


def test_missing_required_activation_is_invalid() -> None:
    results = [
        result
        for result in passing_fault_results()
        if result.layer is not AssertionLayer.ACTIVATION
    ]

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.INVALID


def test_failed_activation_is_invalid() -> None:
    results = passing_fault_results()
    results[1] = make_assertion(
        "gnss_updates_stopped",
        AssertionLayer.ACTIVATION,
        CheckOutcome.FAILED,
    )

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.INVALID


def test_failed_precondition_is_invalid() -> None:
    results = passing_fault_results()
    results[0] = make_assertion(
        "vehicle_ready",
        AssertionLayer.PRECONDITION,
        CheckOutcome.FAILED,
    )

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.INVALID


def test_failed_response_after_valid_activation_fails() -> None:
    results = passing_fault_results()
    results[2] = make_assertion(
        "failsafe_selected",
        AssertionLayer.RESPONSE,
        CheckOutcome.FAILED,
    )

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.FAIL


def test_passing_fault_scenario_passes() -> None:
    status = classify_run(
        passing_fault_results(),
        requires_activation=True,
    )

    assert status is ResultStatus.PASS


def test_baseline_can_pass_without_activation() -> None:
    results = [
        make_assertion(
            "vehicle_ready",
            AssertionLayer.PRECONDITION,
            CheckOutcome.PASSED,
        ),
        make_assertion(
            "mission_completed",
            AssertionLayer.OUTCOME,
            CheckOutcome.PASSED,
        ),
    ]

    status = classify_run(
        results,
        requires_activation=False,
    )

    assert status is ResultStatus.PASS


def test_assertion_error_produces_error() -> None:
    results = passing_fault_results()
    results.append(
        make_assertion(
            "ulog_parsed",
            AssertionLayer.OUTCOME,
            CheckOutcome.ERROR,
        )
    )

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.ERROR


def test_unevaluated_behavior_produces_error() -> None:
    results = passing_fault_results()
    results[2] = make_assertion(
        "failsafe_selected",
        AssertionLayer.RESPONSE,
        CheckOutcome.NOT_EVALUATED,
    )

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.ERROR


def test_run_without_behavior_assertions_is_error() -> None:
    results = passing_fault_results()[:2]

    status = classify_run(
        results,
        requires_activation=True,
    )

    assert status is ResultStatus.ERROR