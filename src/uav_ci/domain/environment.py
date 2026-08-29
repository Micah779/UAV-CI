# typed definitions for supported execution environments

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from uav_ci.domain.scenario import (
    EnvironmentProfileId,
    Identifier,
)


GitRevision = Annotated[
    str,
    Field(pattern=r"^[a-f0-9]{40}$"),
]

Sha256Digest = Annotated[
    str,
    Field(pattern=r"^[a-f0-9]{64}$"),
]


class Px4EnvironmentSpec(BaseModel):
    # pinned PX4 source and build configuration

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    repository: Literal["PX4-Autopilot"]
    revision: GitRevision
    description: str = Field(min_length=1)
    gazebo_models_revision: GitRevision

    require_clean_worktree: Literal[True]

    build_target: Literal["px4_sitl"]
    simulation_target: Literal["gz_x500"]

    @property
    def launch_command(
        self,
    ) -> tuple[str, str, str]:
        return (
            "make",
            self.build_target,
            self.simulation_target,
        )

class GazeboEnvironmentSpec(BaseModel):
    # supported Gazebo runtime configuration

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
    )
    world: Literal["default"]


class VehicleEnvironmentSpec(BaseModel):
    # vehicle model used by the initial environment

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    model: Literal["x500"]


class MavsdkEnvironmentSpec(BaseModel):
    # MAVSDK connection used by the harness

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    system_address: Literal["udpin://0.0.0.0:14540"]


class EnvironmentPatchSpec(BaseModel):
    # a versioned patch for one environment capability

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    patch_id: Identifier
    applies_to: Literal["wind"]
    file: Path
    sha256: Sha256Digest
    target: Path
    description: str = Field(min_length=1)

    @field_validator("file")
    @classmethod
    def patch_file_must_be_safe(
        cls,
        value: Path,
    ) -> Path:
        if value.is_absolute():
            raise ValueError(
                "patch file must be repository-relative"
            )

        if ".." in value.parts:
            raise ValueError(
                "patch file cannot leave the repository"
            )

        if tuple(value.parts[:2]) != (
            "environments",
            "patches",
        ):
            raise ValueError(
                "patch file must be under "
                "environments/patches/"
            )

        if value.suffix != ".patch":
            raise ValueError(
                "patch file must use the .patch extension"
            )

        return value

    @field_validator("target")
    @classmethod
    def patch_target_must_be_safe(
        cls,
        value: Path,
    ) -> Path:
        if value.is_absolute():
            raise ValueError(
                "patch target must be PX4-relative"
            )

        if ".." in value.parts:
            raise ValueError(
                "patch target cannot leave PX4"
            )

        if tuple(value.parts[:3]) != (
            "Tools",
            "simulation",
            "gz",
        ):
            raise ValueError(
                "patch target must be under "
                "Tools/simulation/gz/"
            )

        if value.suffix != ".sdf":
            raise ValueError(
                "patch target must be an SDF file"
            )

        return value


class EnvironmentProfile(BaseModel):
    # complete supported simulator environment contract

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal[1]
    profile_id: EnvironmentProfileId

    px4: Px4EnvironmentSpec
    gazebo: GazeboEnvironmentSpec
    vehicle: VehicleEnvironmentSpec
    mavsdk: MavsdkEnvironmentSpec

    patches: tuple[EnvironmentPatchSpec, ...] = ()

    @model_validator(mode="after")
    def patch_declarations_must_be_unique(self) -> Self:
        patch_ids = [
            patch.patch_id
            for patch in self.patches
        ]
        capabilities = [
            patch.applies_to
            for patch in self.patches
        ]

        if len(patch_ids) != len(set(patch_ids)):
            raise ValueError(
                "environment patch IDs must be unique"
            )

        if len(capabilities) != len(set(capabilities)):
            raise ValueError(
                "each capability may declare only one patch"
            )

        return self