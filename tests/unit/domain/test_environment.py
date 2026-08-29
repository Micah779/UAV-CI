# tests for the known PX4/Gazebo environment contract

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
import yaml

from uav_ci.domain.environment import (
    EnvironmentProfile,
)


PROJECT_ROOT = Path(__file__).parents[3]
PROFILE_PATH = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)

PX4_REVISION = (
    "e4a0bc726e20a6796c08786e3199771c5c914499"
)
GAZEBO_MODELS_REVISION = (
    "bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9"
)
PATCH_HASH = (
    "ec27587df8f351b8ea3166c4d8d49c12"
    "ffabbd676ecc4cfbde52a1b1e0c71712"
)


def patch_data() -> dict[str, object]:
    return {
        "patch_id": "x500_enable_wind",
        "applies_to": "wind",
        "file": (
            "environments/patches/"
            "x500-enable-wind.patch"
        ),
        "sha256": PATCH_HASH,
        "target": (
            "Tools/simulation/gz/"
            "models/x500_base/model.sdf"
        ),
        "description": (
            "Enable Gazebo wind effects on the "
            "X500 base link."
        ),
    }


def known_profile_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile_id": "px4-gz-x500-v1",
        "px4": {
            "repository": "PX4-Autopilot",
            "revision": PX4_REVISION,
            "description": (
                "v1.18.0-beta1-416-ge4a0bc726e"
            ),
            "gazebo_models_revision": (
                GAZEBO_MODELS_REVISION
            ),
            "require_clean_worktree": True,
            "build_target": "px4_sitl",
            "simulation_target": "gz_x500",
        },
        "gazebo": {
            "version": "8.15.0",
            "world": "default",
        },
        "vehicle": {
            "model": "x500",
        },
        "mavsdk": {
            "system_address": "udp://:14540",
        },
        "patches": [
            patch_data(),
        ],
    }


def test_committed_environment_profile_is_valid() -> None:
    raw_data = yaml.safe_load(
        PROFILE_PATH.read_text(encoding="utf-8")
    )

    profile = EnvironmentProfile.model_validate(
        raw_data
    )

    assert profile.profile_id == "px4-gz-x500-v1"
    assert profile.px4.revision == PX4_REVISION
    assert (
        profile.px4.gazebo_models_revision
        == GAZEBO_MODELS_REVISION
    )
    assert profile.gazebo.version == "8.15.0"
    assert profile.vehicle.model == "x500"
    assert profile.mavsdk.system_address == (
        "udp://:14540"
    )
    assert profile.px4.launch_command == (
        "make",
        "px4_sitl",
        "gz_x500",
    )
    assert profile.patches[0].sha256 == PATCH_HASH


def test_unsupported_profile_id_is_rejected() -> None:
    data = known_profile_data()
    data["profile_id"] = "px4-gz-iris-v1"

    with pytest.raises(ValidationError):
        EnvironmentProfile.model_validate(data)


def test_invalid_git_revisions_are_rejected() -> None:
    invalid_revisions = (
        "bb0b9cf",
        "G" * 40,
        "a" * 39,
        "a" * 41,
    )

    for revision in invalid_revisions:
        data = deepcopy(known_profile_data())
        px4 = data["px4"]
        assert isinstance(px4, dict)
        px4["revision"] = revision

        with pytest.raises(ValidationError):
            EnvironmentProfile.model_validate(data)


def test_clean_worktree_is_required() -> None:
    data = deepcopy(known_profile_data())
    px4 = data["px4"]
    assert isinstance(px4, dict)
    px4["require_clean_worktree"] = False

    with pytest.raises(ValidationError):
        EnvironmentProfile.model_validate(data)


def test_unsafe_patch_paths_are_rejected() -> None:
    invalid_paths = (
        {
            "file": "../wind.patch",
        },
        {
            "file": "/tmp/wind.patch",
        },
        {
            "file": "patches/wind.patch",
        },
        {
            "target": "../../model.sdf",
        },
        {
            "target": "/tmp/model.sdf",
        },
        {
            "target": "models/x500/model.sdf",
        },
    )

    for invalid_path in invalid_paths:
        data = known_profile_data()
        patch = patch_data()
        patch.update(invalid_path)
        data["patches"] = [patch]

        with pytest.raises(ValidationError):
            EnvironmentProfile.model_validate(data)


def test_duplicate_patch_declarations_are_rejected() -> None:
    duplicate_id = patch_data()
    duplicate_capability = patch_data()
    duplicate_capability["patch_id"] = (
        "another_wind_patch"
    )

    invalid_patch_lists = (
        [
            patch_data(),
            duplicate_id,
        ],
        [
            patch_data(),
            duplicate_capability,
        ],
    )

    for patches in invalid_patch_lists:
        data = known_profile_data()
        data["patches"] = patches

        with pytest.raises(ValidationError):
            EnvironmentProfile.model_validate(data)


def test_unknown_environment_field_is_rejected() -> None:
    data = known_profile_data()
    data["qgroundcontrol"] = {
        "required": True,
    }

    with pytest.raises(ValidationError):
        EnvironmentProfile.model_validate(data)


def test_environment_profile_is_immutable() -> None:
    profile = EnvironmentProfile.model_validate(
        known_profile_data()
    )

    with pytest.raises(ValidationError):
        profile.profile_id = "changed"