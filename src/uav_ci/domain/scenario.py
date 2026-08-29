# Typed scenario definitions for UAV-CI

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]

class EnvironmentRef(BaseModel):
    # references one supported execution enviornment

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    profile: Literal["px4-gz-x500-v1"]


class ExecutionSpec(BaseModel):
    # defines bounded and reproducible execution settings

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    startup_timeout_s: int = Field(
        default=120,
        gt=0,
        strict=True,
    )
    run_timeout_s: int = Field(
        default=600,
        gt=0,
        strict=True,
    )
    repetitions: int = Field(
        default=1,
        ge=1,
        strict=True,
    )
    seed: int | None = Field(
        default=None,
        ge=0,
        strict=True,
    )


class NoStimulusSpec(BaseModel):
    # represents a baseline scenario without fault injection

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    type: Literal["none"] = "none"


class FaultStimulusSpec(BaseModel):
    # identifies a supported fault and its activation checks

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    type: Literal[
        "wind",
        "gnss_loss",
        "data_link_loss",
        "simulated_battery_drain",
        "unsafe_action_attempt",
    ]
    activation_check_ids: tuple[Identifier, ...] = Field(
        min_length=1,
    )

StimulusSpec = Annotated[
    NoStimulusSpec | FaultStimulusSpec,
    Field(discriminator="type"),
]


class ScenarioSpec(BaseModel):
    # defines the foundational contract for one UAV-CI scenario

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal[1]
    scenario_id: Identifier
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    environment: EnvironmentRef
    execution: ExecutionSpec = Field(
        default_factory=ExecutionSpec,
    )
    stimulus: StimulusSpec

    @property
    def requires_activation(self) -> bool:
        # return whether this scenario requires activation evidence
        
        return isinstance(self.stimulus, FaultStimulusSpec)