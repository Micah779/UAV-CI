'''
Typed references to evidence produced during a UAV-CI run.

- defines how UAV-CI refers to proof
- evidence can come from Gazebo, MAVSDK, telemetry, ULog, the harness itself
- every reference needs a timestamp and clock domain so UAV-CI can interpret timing.
'''

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from uav_ci.domain.enums import ClockDomain, EvidenceSource

class EvidenceRef(BaseModel):
    # identifies evidence supporting an assertion result

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    source: EvidenceSource
    clock_domain: ClockDomain
    timestamp_us: int = Field(ge=0, strict=True)
    signal: str = Field(min_length=1)
    artifact_path: Path | None = None
    description: str = Field(min_length=1)

    @field_validator("artifact_path")
    @classmethod
    def artifact_path_must_be_safe(
        cls,
        value: Path | None,
    ) -> Path | None:
        if value is None:
            return None
        
        if value == Path("."):
            raise ValueError("artifact path cannot be empty")

        if value.is_absolute():
            raise ValueError("artifact path must be relative")

        if ".." in value.parts:
            raise ValueError("artifact path cannot leave the run directory")

        return value

