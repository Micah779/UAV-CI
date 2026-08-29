# Typed scenario definitions for UAV-CI

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]

ParameterName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=16,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    ),
]

ParameterValue = StrictInt | StrictFloat

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


class MissionSpec(BaseModel):
    # references a mission and bounds mission operations

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    file: Path
    upload_timeout_s: int = Field(
        default=30,
        gt=0,
        strict=True,
    )
    completion_timeout_s: int = Field(
        default=300,
        gt=0,
        strict=True,
    )

    @field_validator("file")
    @classmethod
    def mission_path_must_be_safe(cls, value: Path) -> Path:
        if value == Path("."):
            raise ValueError("mission path cannot be empty")

        if value.is_absolute():
            raise ValueError("mission path must be relative")

        if ".." in value.parts:
            raise ValueError(
                "mission path cannot leave the repository"
            )
        
        if not value.parts or value.parts[0] != "missions":
            raise ValueError(
                "mission file must be under missions/"
            )

        if value.suffix != ".plan":
            raise ValueError(
                "mission file must use the .plan extension"
            )

        return value

class ParameterOverride(BaseModel):
    # defines one typed PX4 parameter override

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: ParameterName
    value: ParameterValue

class ParameterPlan(BaseModel):
    # defines parameter overrides and restoration behavior

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    overrides: tuple[ParameterOverride, ...] = ()
    restore: Literal["snapshot"] = "snapshot"

    @model_validator(mode="after")
    def parameter_names_must_be_unique(self) -> Self:
        names = [
            override.name
            for override in self.overrides
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "parameter names must be unique"
            )

        return self


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
    mission: MissionSpec
    parameters: ParameterPlan = Field(
        default_factory=ParameterPlan,
    )
    stimulus: StimulusSpec

    @model_validator(mode="after")
    def mission_must_fit_run_timeout(self) -> Self:
        mission_budget = (
            self.mission.upload_timeout_s
            + self.mission.completion_timeout_s
        )

        if mission_budget > self.execution.run_timeout_s:
            raise ValueError(
                "mission time budget cannot exceed run timeout"
            )

        return self

    @property
    def requires_activation(self) -> bool:
        # return whether this scenario requires activation evidence
        
        return isinstance(self.stimulus, FaultStimulusSpec)