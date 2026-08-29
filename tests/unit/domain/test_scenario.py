'''
it proves:
- a baseline scenario parses correctly.
- a fault scenario requires activation.
- only the known environment is accepted.
- fault scenarios cannot omit activation checks.
- unknown stimulus types are rejected.
- execution limits are positive.
- unknown fields are rejected.
- scenarios are immutable.
'''

import pytest
from pydantic import ValidationError

from uav_ci.domain.scenario import (
    FaultStimulusSpec,
    NoStimulusSpec,
    ScenarioSpec,
)


def baseline_scenario_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "scenario_id": "baseline_mission",
        "title": "Baseline Mission",
        "description": "Execute the known nominal X500 mission.",
        "environment": {
            "profile": "px4-gz-x500-v1",
        },
        "execution": {
            "startup_timeout_s": 120,
            "run_timeout_s": 600,
            "repetitions": 1,
            "seed": 42,
        },
        "stimulus": {
            "type": "none",
        },
    }


def fault_scenario_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "scenario_id": "gnss_loss",
        "title": "GNSS Loss",
        "description": "Verify the X500 response to GNSS loss.",
        "environment": {
            "profile": "px4-gz-x500-v1",
        },
        "execution": {
            "startup_timeout_s": 120,
            "run_timeout_s": 600,
            "repetitions": 1,
            "seed": 42,
        },
        "stimulus": {
            "type": "gnss_loss",
            "activation_check_ids": [
                "gnss_updates_stopped",
            ],
        },
    }


def test_valid_baseline_does_not_require_activation() -> None:
    scenario = ScenarioSpec.model_validate(
        baseline_scenario_data()
    )

    assert isinstance(scenario.stimulus, NoStimulusSpec)
    assert scenario.requires_activation is False
    assert scenario.execution.repetitions == 1


def test_valid_fault_requires_activation() -> None:
    scenario = ScenarioSpec.model_validate(
        fault_scenario_data()
    )

    assert isinstance(scenario.stimulus, FaultStimulusSpec)
    assert scenario.requires_activation is True
    assert scenario.stimulus.activation_check_ids == (
        "gnss_updates_stopped",
    )


def test_unknown_environment_is_rejected() -> None:
    data = baseline_scenario_data()
    data["environment"] = {
        "profile": "px4-gz-iris-v1",
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_fault_without_activation_checks_is_rejected() -> None:
    data = fault_scenario_data()
    data["stimulus"] = {
        "type": "gnss_loss",
        "activation_check_ids": [],
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_unknown_stimulus_type_is_rejected() -> None:
    data = fault_scenario_data()
    data["stimulus"] = {
        "type": "motor_failure",
        "activation_check_ids": [
            "motor_failure_detected",
        ],
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_invalid_execution_limits_are_rejected() -> None:
    invalid_executions = (
        {
            "startup_timeout_s": 0,
            "run_timeout_s": 600,
            "repetitions": 1,
        },
        {
            "startup_timeout_s": 120,
            "run_timeout_s": -1,
            "repetitions": 1,
        },
        {
            "startup_timeout_s": 120,
            "run_timeout_s": 600,
            "repetitions": 0,
        },
    )

    for execution in invalid_executions:
        data = baseline_scenario_data()
        data["execution"] = execution

        with pytest.raises(ValidationError):
            ScenarioSpec.model_validate(data)


def test_unknown_scenario_field_is_rejected() -> None:
    data = baseline_scenario_data()
    data["vehicle"] = "another_vehicle"

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_scenario_is_immutable() -> None:
    scenario = ScenarioSpec.model_validate(
        baseline_scenario_data()
    )

    with pytest.raises(ValidationError):
        scenario.title = "Changed title"