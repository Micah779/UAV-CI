# tests for the repository-owned wind scenario

from hashlib import sha256
from pathlib import Path

from uav_ci.domain.enums import (
    AssertionLayer,
)
from uav_ci.domain.scenario import (
    WindStimulusSpec,
)
from uav_ci.scenario import load_scenario


PROJECT_ROOT = Path(__file__).parents[3]
WIND_SCENARIO = (
    PROJECT_ROOT / "scenarios/wind.yaml"
)
BASELINE_MISSION = (
    PROJECT_ROOT / "missions/baseline.plan"
)


def test_repository_wind_scenario_loads(
) -> None:
    loaded = load_scenario(
        WIND_SCENARIO
    )
    scenario = loaded.scenario

    assert scenario.scenario_id == (
        "wind_tracking"
    )
    assert isinstance(
        scenario.stimulus,
        WindStimulusSpec,
    )
    assert scenario.requires_activation is True
    assert loaded.mission_path == (
        BASELINE_MISSION.resolve()
    )
    assert loaded.mission_hash == sha256(
        BASELINE_MISSION.read_bytes()
    ).hexdigest()


def test_wind_activation_matches_stimulus(
) -> None:
    scenario = load_scenario(
        WIND_SCENARIO
    ).scenario
    stimulus = scenario.stimulus

    assert isinstance(
        stimulus,
        WindStimulusSpec,
    )

    activation = next(
        assertion
        for assertion in scenario.assertions
        if (
            assertion.layer
            is AssertionLayer.ACTIVATION
        )
    )

    assert activation.assertion_id == (
        "wind_reached_vehicle"
    )
    assert activation.expected == (
        stimulus.minimum_proven_speed_m_s
    )
    assert activation.within_s == (
        stimulus.activation_timeout_s
    )


def test_wind_scenario_has_behavior_assertion(
) -> None:
    scenario = load_scenario(
        WIND_SCENARIO
    ).scenario

    behavior_assertions = tuple(
        assertion
        for assertion in scenario.assertions
        if assertion.layer
        in {
            AssertionLayer.RESPONSE,
            AssertionLayer.OUTCOME,
        }
    )

    assert behavior_assertions
    assert (
        behavior_assertions[0].assertion_id
        == "vehicle_landed"
    )