# independently tests mission paths, timeout bounds, parameter types, names, duplicate detection, and restoration policy

from pathlib import Path

import pytest
from pydantic import ValidationError

from uav_ci.domain.scenario import (
    MissionSpec,
    ParameterPlan,
)


def test_valid_mission_reference_is_parsed() -> None:
    mission = MissionSpec.model_validate(
        {
            "file": "missions/baseline.plan",
            "upload_timeout_s": 30,
            "completion_timeout_s": 300,
        }
    )

    assert mission.file == Path("missions/baseline.plan")
    assert mission.upload_timeout_s == 30
    assert mission.completion_timeout_s == 300


def test_unsafe_mission_paths_are_rejected() -> None:
    unsafe_paths = (
        "/tmp/baseline.plan",
        "../baseline.plan",
        "missions/../../baseline.plan",
        "plans/baseline.plan",
        "missions/baseline.yaml",
        "",
    )

    for unsafe_path in unsafe_paths:
        with pytest.raises(ValidationError):
            MissionSpec.model_validate(
                {
                    "file": unsafe_path,
                    "upload_timeout_s": 30,
                    "completion_timeout_s": 300,
                }
            )


def test_nonpositive_mission_timeouts_are_rejected() -> None:
    invalid_timeouts = (
        {
            "upload_timeout_s": 0,
            "completion_timeout_s": 300,
        },
        {
            "upload_timeout_s": 30,
            "completion_timeout_s": -1,
        },
    )

    for timeouts in invalid_timeouts:
        with pytest.raises(ValidationError):
            MissionSpec.model_validate(
                {
                    "file": "missions/baseline.plan",
                    **timeouts,
                }
            )


def test_valid_parameter_overrides_are_typed() -> None:
    plan = ParameterPlan.model_validate(
        {
            "overrides": [
                {
                    "name": "COM_LOW_BAT_ACT",
                    "value": 3,
                },
                {
                    "name": "SIM_BAT_DRAIN",
                    "value": 240.0,
                },
            ],
            "restore": "snapshot",
        }
    )

    assert plan.overrides[0].value == 3
    assert isinstance(plan.overrides[0].value, int)
    assert plan.overrides[1].value == 240.0
    assert isinstance(plan.overrides[1].value, float)


def test_invalid_parameter_value_types_are_rejected() -> None:
    invalid_values = (
        True,
        "3",
        "enabled",
    )

    for invalid_value in invalid_values:
        with pytest.raises(ValidationError):
            ParameterPlan.model_validate(
                {
                    "overrides": [
                        {
                            "name": "COM_LOW_BAT_ACT",
                            "value": invalid_value,
                        }
                    ]
                }
            )


def test_invalid_parameter_names_are_rejected() -> None:
    invalid_names = (
        "com_low_bat_act",
        "2ND_PARAMETER",
        "PARAMETER_NAME_TOO_LONG",
        "BAD-NAME",
    )

    for invalid_name in invalid_names:
        with pytest.raises(ValidationError):
            ParameterPlan.model_validate(
                {
                    "overrides": [
                        {
                            "name": invalid_name,
                            "value": 1,
                        }
                    ]
                }
            )


def test_duplicate_parameter_names_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ParameterPlan.model_validate(
            {
                "overrides": [
                    {
                        "name": "SIM_BAT_DRAIN",
                        "value": 240,
                    },
                    {
                        "name": "SIM_BAT_DRAIN",
                        "value": 120,
                    },
                ]
            }
        )


def test_only_snapshot_restoration_is_supported() -> None:
    with pytest.raises(ValidationError):
        ParameterPlan.model_validate(
            {
                "overrides": [],
                "restore": "none",
            }
        )