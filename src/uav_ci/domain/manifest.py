# immutable identity and provenance for UAV-CI runs

from datetime import timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from uav_ci.domain.scenario import (
    EnvironmentProfileId,
)


class HarnessProvenance(BaseModel):
    # software environment that created a run

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    uav_ci_version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)


class RunManifest(BaseModel):
    # immutable identity and requested configuration of one run

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal[1] = 1
    run_id: UUID

    scenario_id: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    scenario_hash: str = Field(
        pattern=r"^[a-f0-9]{64}$",
    )

    environment_profile: EnvironmentProfileId
    requires_activation: bool = Field(strict=True)

    repetition_index: int = Field(
        ge=1,
        strict=True,
    )
    repetition_count: int = Field(
        ge=1,
        strict=True,
    )
    seed: int | None = Field(
        default=None,
        ge=0,
        strict=True,
    )

    started_at: AwareDatetime
    harness: HarnessProvenance

    @model_validator(mode="after")
    def validate_run_identity(self) -> Self:
        if self.repetition_index > self.repetition_count:
            raise ValueError(
                "repetition_index cannot exceed "
                "repetition_count"
            )

        if self.started_at.utcoffset() != timedelta(0):
            raise ValueError(
                "started_at must use UTC"
            )

        return self