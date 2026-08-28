# typed results produced by UAV-CI assertions

from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from uav_ci.domain.enums import AssertionLayer, CheckOutcome, ResultStatus
from uav_ci.domain.evidence import EvidenceRef

class AssertionResult(BaseModel):
    # describes the outcome and evidence for one assertion

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    assertion_id: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    layer: AssertionLayer
    outcome: CheckOutcome
    message: str = Field(min_length=1)
    # tuple since the result is immutable
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def evaluated_outcome_requires_evidence(self) -> Self:
        evaluated_outcomes = {
            CheckOutcome.PASSED,
            CheckOutcome.FAILED,
        }

        if self.outcome in evaluated_outcomes and not self.evidence:
            raise ValueError(
                "passed and failed assertions must include evidence"
            )
            
        return self

def classify_run(
    assertions: Sequence[AssertionResult],
    *,
    requires_activation: bool,
    harness_error: bool = False,
    unsupported_environment: bool = False,
) -> ResultStatus:
    # derive the final run status from assertion results

    if harness_error:
        return ResultStatus.ERROR

    if unsupported_environment:
        return ResultStatus.SKIPPED

    if not assertions:
        return ResultStatus.ERROR

    if any(
        result.outcome is CheckOutcome.ERROR
        for result in assertions
    ):
        return ResultStatus.ERROR

    precondition_results = [
        result
        for result in assertions
        if result.layer is AssertionLayer.PRECONDITION
    ]

    if any(
        result.outcome is not CheckOutcome.PASSED
        for result in precondition_results
    ):
        return ResultStatus.INVALID

    activation_results = [
        result
        for result in assertions
        if result.layer is AssertionLayer.ACTIVATION
    ]

    if requires_activation and not activation_results:
        return ResultStatus.INVALID

    if any(
        result.outcome is not CheckOutcome.PASSED
        for result in activation_results
    ):
        return ResultStatus.INVALID

    behavior_results = [
        result
        for result in assertions
        if result.layer
        in {
            AssertionLayer.RESPONSE,
            AssertionLayer.OUTCOME,
        }
    ]

    if not behavior_results:
        return ResultStatus.ERROR

    if any(
        result.outcome is CheckOutcome.NOT_EVALUATED
        for result in behavior_results
    ):
        return ResultStatus.ERROR

    if any(
        result.outcome is CheckOutcome.FAILED
        for result in behavior_results
    ):
        return ResultStatus.FAIL

    return ResultStatus.PASS
