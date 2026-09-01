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
    StrictBool,
    StrictStr,
)

from uav_ci.domain.enums import (
    AssertionLayer,
    ComparisonOperator,
    EvidenceSource,
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

EnvironmentProfileId = Literal[
    "px4-gz-x500-v1",
]

FaultType = Literal[
    "wind",
    "gnss_loss",
    "data_link_loss",
    "simulated_battery_drain",
    "unsafe_action_attempt",
]

NumericValue = StrictInt | StrictFloat
ParameterValue = NumericValue

AssertionValue = (
    StrictBool
    | StrictInt
    | StrictFloat
    | StrictStr
)

class EnvironmentRef(BaseModel):
    # references one supported execution enviornment

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    profile: EnvironmentProfileId


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
        allow_inf_nan=False,
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


class AssertionSpec(BaseModel):
    # defines one declarative scenario assertion

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    assertion_id: Identifier
    layer: AssertionLayer
    source: EvidenceSource
    signal: str = Field(min_length=1)
    operator: ComparisonOperator
    expected: AssertionValue | None = None
    within_s: NumericValue | None = None
    tolerance: NumericValue | None = None
    description: str = Field(min_length=1)

    @field_validator("within_s")
    @classmethod
    def within_s_must_be_positive(
        cls,
        value: NumericValue | None,
    ) -> NumericValue | None:
        if value is not None and value <= 0:
            raise ValueError("within_s must be positive")

        return value

    @field_validator("tolerance")
    @classmethod
    def tolerance_must_be_nonnegative(
        cls,
        value: NumericValue | None,
    ) -> NumericValue | None:
        if value is not None and value < 0:
            raise ValueError("tolerance cannot be negative")

        return value

    @model_validator(mode="after")
    def validate_operator_fields(self) -> Self:
        if self.operator is ComparisonOperator.EXISTS:
            if self.expected is not None:
                raise ValueError(
                    "exists assertions cannot define expected"
                )

            if self.tolerance is not None:
                raise ValueError(
                    "exists assertions cannot define tolerance"
                )

            return self

        if self.expected is None:
            raise ValueError(
                "comparison assertions must define expected"
            )

        if (
            self.tolerance is not None
            and type(self.expected) not in {int, float}
        ):
            raise ValueError(
                "tolerance requires a numeric expected value"
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
    # shared requirements for every injected fault

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    activation_check_ids: tuple[
        Identifier,
        ...,
    ] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def activation_check_ids_must_be_unique(
        self,
    ) -> Self:
        if len(self.activation_check_ids) != len(
            set(self.activation_check_ids)
        ):
            raise ValueError(
                "activation check IDs must be unique"
            )

        return self


class WindStimulusSpec(FaultStimulusSpec):
    # controlled Gazebo world-frame wind stimulus

    type: Literal["wind"]
    method: Literal[
        "gazebo_transport"
    ] = "gazebo_transport"
    trigger: Literal["airborne"] = "airborne"

    speed_m_s: NumericValue = Field(
        gt=0,
    )
    direction_from_world_x_deg: (
        NumericValue
    ) = Field(
        ge=0,
        lt=360,
    )
    minimum_proven_speed_m_s: (
        NumericValue
    ) = Field(
        gt=0,
    )
    activation_timeout_s: int = Field(
        default=5,
        gt=0,
        strict=True,
    )

    @model_validator(mode="after")
    def proof_threshold_must_be_reachable(
        self,
    ) -> Self:
        if (
            self.minimum_proven_speed_m_s
            > self.speed_m_s
        ):
            raise ValueError(
                "minimum proven wind speed cannot "
                "exceed commanded wind speed"
            )

        return self


class RuntimeFaultStimulusSpec(
    FaultStimulusSpec,
):
    # fault types whose detailed schemas come later

    type: Literal[
        "gnss_loss",
        "data_link_loss",
        "simulated_battery_drain",
        "unsafe_action_attempt",
    ]


StimulusSpec = Annotated[
    (
        NoStimulusSpec
        | WindStimulusSpec
        | RuntimeFaultStimulusSpec
    ),
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
    assertions: tuple[AssertionSpec, ...] = Field(
        min_length=1,
    )

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

    # enforces assertion ID uniqueness, baseline, fault reference etc.
    @model_validator(mode="after")
    def validate_assertion_contract(self) -> Self:
        assertion_ids = [
            assertion.assertion_id
            for assertion in self.assertions
        ]

        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError(
                "assertion IDs must be unique"
            )

        assertion_by_id = {
            assertion.assertion_id: assertion
            for assertion in self.assertions
        }

        activation_ids = {
            assertion.assertion_id
            for assertion in self.assertions
            if assertion.layer is AssertionLayer.ACTIVATION
        }

        if isinstance(self.stimulus, NoStimulusSpec):
            if activation_ids:
                raise ValueError(
                    "baseline scenarios cannot define "
                    "activation assertions"
                )
        else:
            referenced_ids = set(
                self.stimulus.activation_check_ids
            )

            missing_ids = (
                referenced_ids - set(assertion_by_id)
            )
            if missing_ids:
                missing = ", ".join(sorted(missing_ids))
                raise ValueError(
                    "activation checks reference undefined "
                    f"assertions: {missing}"
                )

            wrong_layer_ids = {
                assertion_id
                for assertion_id in referenced_ids
                if (
                    assertion_by_id[assertion_id].layer
                    is not AssertionLayer.ACTIVATION
                )
            }
            if wrong_layer_ids:
                wrong = ", ".join(
                    sorted(wrong_layer_ids)
                )
                raise ValueError(
                    "activation checks must reference "
                    f"activation assertions: {wrong}"
                )

            unreferenced_ids = (
                activation_ids - referenced_ids
            )
            if unreferenced_ids:
                unreferenced = ", ".join(
                    sorted(unreferenced_ids)
                )
                raise ValueError(
                    "activation assertions must be referenced "
                    f"by the stimulus: {unreferenced}"
                )

        behavior_layers = {
            AssertionLayer.RESPONSE,
            AssertionLayer.OUTCOME,
        }

        if not any(
            assertion.layer in behavior_layers
            for assertion in self.assertions
        ):
            raise ValueError(
                "a scenario must define at least one "
                "response or outcome assertion"
            )

        return self

    @model_validator(mode="after")
    def validate_wind_activation_contract(
        self,
    ) -> Self:
        if not isinstance(
            self.stimulus,
            WindStimulusSpec,
        ):
            return self

        required_activation_ids = (
            "wind_reached_vehicle",
        )

        if (
            self.stimulus.activation_check_ids
            != required_activation_ids
        ):
            raise ValueError(
                "wind stimulus must use the "
                "wind_reached_vehicle activation "
                "check"
            )

        assertion_by_id = {
            assertion.assertion_id: assertion
            for assertion in self.assertions
        }
        activation = assertion_by_id[
            "wind_reached_vehicle"
        ]

        supported_contract = all(
            (
                activation.layer
                is AssertionLayer.ACTIVATION,
                activation.source
                is EvidenceSource.SIMULATOR,
                activation.signal
                == "gazebo.wind.speed_m_s",
                activation.operator
                is (
                    ComparisonOperator
                    .GREATER_THAN_OR_EQUAL
                ),
                activation.expected
                == (
                    self.stimulus
                    .minimum_proven_speed_m_s
                ),
                activation.within_s
                == (
                    self.stimulus
                    .activation_timeout_s
                ),
                activation.tolerance is None,
            )
        )

        if not supported_contract:
            raise ValueError(
                "wind activation assertion does "
                "not match the wind stimulus "
                "proof contract"
            )

        return self
        
    @property
    def requires_activation(self) -> bool:
        # return whether this scenario requires activation evidence
        
        return isinstance(self.stimulus, FaultStimulusSpec)