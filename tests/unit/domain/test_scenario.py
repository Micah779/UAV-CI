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
    WindStimulusSpec,
)

def landed_assertion_data() -> dict[str, object]:
    return {
        "assertion_id": "vehicle_landed",
        "layer": "outcome",
        "source": "ulog",
        "signal": "vehicle_land_detected.landed",
        "operator": "equal",
        "expected": True,
        "description": "The vehicle reaches a landed state.",
    }


def gnss_activation_assertion_data() -> dict[str, object]:
    return {
        "assertion_id": "gnss_updates_stopped",
        "layer": "activation",
        "source": "telemetry",
        "signal": "vehicle_gps_position.fix_type",
        "operator": "less_than",
        "expected": 3,
        "within_s": 2,
        "description": (
            "GNSS loss is observed after fault injection."
        ),
    }

def wind_activation_assertion_data(
) -> dict[str, object]:
    return {
        "assertion_id": (
            "wind_reached_vehicle"
        ),
        "layer": "activation",
        "source": "simulator",
        "signal": "gazebo.wind.speed_m_s",
        "operator": (
            "greater_than_or_equal"
        ),
        "expected": 4.5,
        "within_s": 5,
        "description": (
            "Gazebo wind at the vehicle reaches "
            "the required speed."
        ),
    }


def wind_scenario_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "scenario_id": "wind_tracking",
        "title": "Wind Tracking",
        "description": (
            "Verify X500 behavior under "
            "controlled Gazebo wind."
        ),
        "environment": {
            "profile": "px4-gz-x500-v1",
        },
        "execution": {
            "startup_timeout_s": 120,
            "run_timeout_s": 600,
            "repetitions": 1,
            "seed": 42,
        },
        "mission": {
            "file": "missions/baseline.plan",
            "upload_timeout_s": 30,
            "completion_timeout_s": 300,
        },
        "stimulus": {
            "type": "wind",
            "method": "gazebo_transport",
            "trigger": "airborne",
            "speed_m_s": 5.0,
            "direction_from_world_x_deg": 90.0,
            "minimum_proven_speed_m_s": 4.5,
            "activation_timeout_s": 5,
            "activation_check_ids": [
                "wind_reached_vehicle",
            ],
        },
        "assertions": [
            wind_activation_assertion_data(),
            landed_assertion_data(),
        ],
    }

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
        "mission": {
            "file": "missions/baseline.plan",
            "upload_timeout_s": 30,
            "completion_timeout_s": 300,
        },
        "stimulus": {
            "type": "none",
        },
        "assertions": [
            landed_assertion_data(),
        ]
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
        "mission": {
            "file": "missions/gnss_loss.plan",
            "upload_timeout_s": 30,
            "completion_timeout_s": 300,
        },
        "stimulus": {
            "type": "gnss_loss",
            "activation_check_ids": [
                "gnss_updates_stopped",
            ],
        },
        "assertions": [
            landed_assertion_data(),
            gnss_activation_assertion_data(),
        ],
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

def test_mission_budget_cannot_exceed_run_timeout() -> None:
    data = baseline_scenario_data()
    data["mission"] = {
        "file": "missions/baseline.plan",
        "upload_timeout_s": 301,
        "completion_timeout_s": 300,
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)

def test_duplicate_assertion_ids_are_rejected() -> None:
    data = baseline_scenario_data()
    data["assertions"] = [
        landed_assertion_data(),
        landed_assertion_data(),
    ]

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_unknown_activation_check_is_rejected() -> None:
    data = fault_scenario_data()
    data["stimulus"] = {
        "type": "gnss_loss",
        "activation_check_ids": [
            "unknown_activation",
        ],
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_activation_check_must_use_activation_layer() -> None:
    data = fault_scenario_data()
    activation = gnss_activation_assertion_data()
    activation["layer"] = "response"

    data["assertions"] = [
        activation,
        landed_assertion_data(),
    ]

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_unreferenced_activation_assertion_is_rejected() -> None:
    data = fault_scenario_data()
    second_activation = gnss_activation_assertion_data()
    second_activation["assertion_id"] = (
        "simulator_gnss_disabled"
    )

    data["assertions"] = [
        gnss_activation_assertion_data(),
        second_activation,
        landed_assertion_data(),
    ]

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_baseline_activation_assertion_is_rejected() -> None:
    data = baseline_scenario_data()
    data["assertions"] = [
        gnss_activation_assertion_data(),
        landed_assertion_data(),
    ]

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_scenario_without_behavior_assertion_is_rejected() -> None:
    data = fault_scenario_data()
    data["assertions"] = [
        gnss_activation_assertion_data(),
    ]

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)


def test_duplicate_activation_check_ids_are_rejected() -> None:
    data = fault_scenario_data()
    data["stimulus"] = {
        "type": "gnss_loss",
        "activation_check_ids": [
            "gnss_updates_stopped",
            "gnss_updates_stopped",
        ],
    }

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(data)

def test_valid_wind_stimulus_is_typed() -> None:
    scenario = ScenarioSpec.model_validate(
        wind_scenario_data()
    )

    stimulus = scenario.stimulus

    assert isinstance(
        stimulus,
        WindStimulusSpec,
    )
    assert isinstance(
        stimulus,
        FaultStimulusSpec,
    )
    assert stimulus.speed_m_s == 5.0
    assert (
        stimulus.direction_from_world_x_deg
        == 90.0
    )
    assert (
        stimulus.minimum_proven_speed_m_s
        == 4.5
    )
    assert stimulus.trigger == "airborne"
    assert scenario.requires_activation is True


def test_wind_speed_must_be_positive() -> None:
    data = wind_scenario_data()
    stimulus = data["stimulus"]

    assert isinstance(stimulus, dict)
    stimulus["speed_m_s"] = 0.0

    with pytest.raises(
        ValidationError,
        match="speed_m_s",
    ):
        ScenarioSpec.model_validate(data)


def test_wind_direction_must_be_normalized(
) -> None:
    for direction in (
        -1.0,
        360.0,
    ):
        data = wind_scenario_data()
        stimulus = data["stimulus"]

        assert isinstance(stimulus, dict)
        stimulus[
            "direction_from_world_x_deg"
        ] = direction

        with pytest.raises(
            ValidationError,
            match=(
                "direction_from_world_x_deg"
            ),
        ):
            ScenarioSpec.model_validate(data)


def test_wind_proof_threshold_must_be_reachable(
) -> None:
    data = wind_scenario_data()
    stimulus = data["stimulus"]

    assert isinstance(stimulus, dict)
    stimulus[
        "minimum_proven_speed_m_s"
    ] = 5.1

    with pytest.raises(
        ValidationError,
        match="cannot exceed",
    ):
        ScenarioSpec.model_validate(data)


def test_non_wind_fault_rejects_wind_fields(
) -> None:
    data = fault_scenario_data()
    stimulus = data["stimulus"]

    assert isinstance(stimulus, dict)
    stimulus["speed_m_s"] = 5.0

    with pytest.raises(
        ValidationError,
        match="Extra inputs",
    ):
        ScenarioSpec.model_validate(data)

def test_wind_activation_threshold_must_match(
) -> None:
    data = wind_scenario_data()
    assertions = data["assertions"]

    assert isinstance(assertions, list)
    activation = assertions[0]

    assert isinstance(activation, dict)
    activation["expected"] = 4.0

    with pytest.raises(
        ValidationError,
        match="proof contract",
    ):
        ScenarioSpec.model_validate(data)


def test_wind_activation_timeout_must_match(
) -> None:
    data = wind_scenario_data()
    assertions = data["assertions"]

    assert isinstance(assertions, list)
    activation = assertions[0]

    assert isinstance(activation, dict)
    activation["within_s"] = 4

    with pytest.raises(
        ValidationError,
        match="proof contract",
    ):
        ScenarioSpec.model_validate(data)


def test_wind_activation_id_is_fixed() -> None:
    data = wind_scenario_data()
    stimulus = data["stimulus"]
    assertions = data["assertions"]

    assert isinstance(stimulus, dict)
    assert isinstance(assertions, list)
    assert isinstance(assertions[0], dict)

    stimulus["activation_check_ids"] = [
        "wind_command_succeeded",
    ]
    assertions[0]["assertion_id"] = (
        "wind_command_succeeded"
    )

    with pytest.raises(
        ValidationError,
        match="wind_reached_vehicle",
    ):
        ScenarioSpec.model_validate(data)