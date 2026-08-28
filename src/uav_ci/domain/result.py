# typed results produced by UAV-CI assertions

from typing import Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from uav_ci.domain.enums import AssertionLayer, CheckOutcome
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
        pattern=r"^[a-z0-9_]*$",
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
                "passed and failed asseritons must include evidence"
            )

        return self