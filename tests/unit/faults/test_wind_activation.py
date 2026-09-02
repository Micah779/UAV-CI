# pure assessment tests; nonzero wind samples here are synthetic

from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path

import pytest

from uav_ci.faults import wind_activation as module
from uav_ci.domain.scenario import WindStimulusSpec
from uav_ci.faults.wind_observer import RecordedWindObservation
from uav_ci.faults.wind_state import decode_wind_state


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gazebo"
START = 100_000_000_000
FINISH = START + 200_000_000


def stimulus(direction=90.0):
    return WindStimulusSpec(
        type="wind",
        speed_m_s=5.0,
        direction_from_world_x_deg=direction,
        minimum_proven_speed_m_s=4.5,
        activation_timeout_s=5,
        activation_check_ids=("wind_reached_vehicle",),
    )


def captured(index=1):
    return decode_wind_state(
        (FIXTURES / f"gazebo-state-{index}.txt").read_text(
            encoding="utf-8",
        )
    )


def baseline():
    return RecordedWindObservation(
        observation=captured(),
        artifact_path=Path("/synthetic-run/evidence/baseline.json"),
        request_started_monotonic_ns=START - 200_000_000,
        request_finished_monotonic_ns=START - 100_000_000,
    )


def sample(
    index,
    velocity=(0.0, 5.0, 0.0),
    seed=(0.0, 5.0, 0.0),
):
    base = captured()
    finished = START + (index + 1) * 1_000_000_000

    return RecordedWindObservation(
        observation=replace(
            base,
            simulation_time_ns=(
                base.simulation_time_ns + index * 1_000_000_000
            ),
            iterations=base.iterations + index * 250,
            wind_velocity_world_m_s=velocity,
            wind_seed_world_m_s=seed,
        ),
        artifact_path=Path(
            f"/synthetic-run/evidence/sample-{index}.json"
        ),
        request_started_monotonic_ns=finished - 100_000_000,
        request_finished_monotonic_ns=finished,
    )


def evaluate(samples, before=None, spec=None, **options):
    settings = dict(
        command_started_monotonic_ns=START,
        command_finished_monotonic_ns=FINISH,
    )
    settings.update(options)

    return module.evaluate_wind_activation(
        spec or stimulus(),
        before or baseline(),
        samples,
        **settings,
    )


def test_two_matching_samples_support_activation():
    before = baseline()
    first, second = sample(1), sample(2)

    result = evaluate([first, second], before=before)

    assert result.activated is True
    assert result.supporting_samples == (before, first, second)

    with pytest.raises(FrozenInstanceError):
        result.activated = False


@pytest.mark.parametrize("count", [0, 1])
def test_insufficient_samples_cannot_prove_activation(count):
    result = evaluate([sample(1)][:count])

    assert result.activated is False
    assert result.supporting_samples == ()


def test_requested_seed_alone_is_not_proof():
    result = evaluate([
        sample(1, velocity=(0, 0, 0)),
        sample(2, velocity=(0, 0, 0)),
    ])

    assert result.activated is False


def test_real_calm_captures_cannot_prove_activation():
    first = replace(
        sample(1),
        observation=captured(2),
    )
    second = replace(
        sample(2),
        observation=replace(
            captured(2),
            simulation_time_ns=11_000_000_000,
            iterations=3000,
        ),
    )

    assert evaluate([first, second]).activated is False


@pytest.mark.parametrize(
    "velocity",
    [
        (0, 4.49, 0),
        (5, 0, 0),
        (0, -5, 0),
        (0, 5, 0.2),
        (0, 5.3, 0),
    ],
)
def test_wrong_actual_wind_is_not_proof(velocity):
    result = evaluate([
        sample(1, velocity),
        sample(2, velocity),
    ])

    assert result.activated is False


def test_threshold_is_inclusive():
    result = evaluate([
        sample(1, (0, 4.5, 0)),
        sample(2, (0, 4.5, 0)),
    ])

    assert result.activated is True


def test_wrong_seed_rejects_even_if_actual_speed_matches():
    result = evaluate([
        sample(1, seed=(0, 4, 0)),
        sample(2, seed=(0, 4, 0)),
    ])

    assert result.activated is False


def test_direction_wraparound():
    angle = math.radians(1)
    velocity = (
        5 * math.cos(angle),
        5 * math.sin(angle),
        0,
    )

    requested = math.radians(359)
    seed = (
        5 * math.cos(requested),
        5 * math.sin(requested),
        0,
    )

    result = evaluate(
        [
            sample(1, velocity, seed),
            sample(2, velocity, seed),
        ],
        spec=stimulus(359),
    )

    assert result.activated is True


def test_serialized_seed_rounding_is_tolerated():
    exact = 5 / math.sqrt(2)
    samples = [
        sample(
            index,
            (exact, exact, 0),
            (3.53553, 3.53553, 0),
        )
        for index in (1, 2)
    ]

    assert evaluate(samples, spec=stimulus(45)).activated is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("paused", True),
        ("link_wind_enabled", False),
        ("wind_velocity_world_m_s", (0, 5, 0)),
        ("wind_seed_world_m_s", (0, 5, 0)),
    ],
)
def test_baseline_must_be_calm_running_and_wind_capable(field, value):
    before = baseline()
    before = replace(
        before,
        observation=replace(
            before.observation,
            **{field: value},
        ),
    )

    result = evaluate(
        [sample(1), sample(2)],
        before=before,
    )

    assert result.activated is False


@pytest.mark.parametrize(
    "finished,reason",
    [
        (START + 1, "overlaps"),
        (START - 1_000_000_001, "too old"),
    ],
)
def test_bad_baseline_timing(finished, reason):
    before = replace(
        baseline(),
        request_started_monotonic_ns=finished - 1,
        request_finished_monotonic_ns=finished,
    )

    result = evaluate(
        [sample(1), sample(2)],
        before=before,
    )

    assert not result.activated
    assert reason in result.reason


@pytest.mark.parametrize(
    "field,value",
    [
        ("world_entity_id", 99),
        ("wind_entity_id", 99),
        ("model_entity_id", 99),
        ("link_entity_id", 99),
        ("paused", True),
        ("link_wind_enabled", False),
    ],
)
def test_unsafe_or_different_target_rejects(field, value):
    second = sample(2)
    second = replace(
        second,
        observation=replace(
            second.observation,
            **{field: value},
        ),
    )

    assert evaluate([sample(1), second]).activated is False


@pytest.mark.parametrize(
    "field",
    ["simulation_time_ns", "iterations"],
)
def test_both_simulator_clocks_must_advance(field):
    first, second = sample(1), sample(2)
    second = replace(
        second,
        observation=replace(
            second.observation,
            **{field: getattr(first.observation, field)},
        ),
    )

    result = evaluate([first, second])

    assert not result.activated
    assert "did not advance" in result.reason


def test_observation_overlapping_command_rejects():
    first = replace(
        sample(1),
        request_started_monotonic_ns=FINISH - 1,
    )

    result = evaluate([first, sample(2)])

    assert "overlaps the command" in result.reason


def test_out_of_order_samples_are_not_sorted_into_a_pass():
    result = evaluate([sample(2), sample(1)])

    assert not result.activated
    assert "out of order" in result.reason


def test_deadline_is_measured_from_command_start():
    late = replace(
        sample(2),
        request_finished_monotonic_ns=START + 5_000_000_001,
    )

    assert "deadline" in evaluate([sample(1), late]).reason


def test_deadline_boundary_is_inclusive():
    last = replace(
        sample(2),
        request_finished_monotonic_ns=START + 5_000_000_000,
    )

    assert evaluate([sample(1), last]).activated is True


def test_command_cannot_restart_activation_budget_on_completion():
    result = evaluate(
        [],
        command_finished_monotonic_ns=START + 6_000_000_000,
    )

    assert not result.activated
    assert "consumed" in result.reason


def test_qualifying_samples_must_be_consecutive():
    samples = [
        sample(1),
        sample(2, (0, 4, 0)),
        sample(3),
    ]

    assert evaluate(samples).activated is False

    result = evaluate([*samples, sample(4)])

    assert result.activated is True
    assert result.supporting_samples[1:] == (
        samples[-1],
        sample(4),
    )


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_bad_command_timestamp_is_input_error(value):
    with pytest.raises(ValueError, match="command timestamps"):
        evaluate(
            [],
            command_started_monotonic_ns=value,
        )


def test_reversed_command_timing_is_input_error():
    with pytest.raises(ValueError, match="command timing"):
        evaluate(
            [],
            command_finished_monotonic_ns=START - 1,
        )


def test_malformed_record_is_input_error():
    broken = sample(
        1,
        velocity=(0, float("nan"), 0),
    )

    with pytest.raises(ValueError, match="finite numbers"):
        evaluate([broken])


def test_nonfinite_stimulus_is_input_error():
    spec = stimulus().model_copy(
        update={"speed_m_s": float("inf")},
    )

    with pytest.raises(ValueError, match="finite"):
        evaluate([], spec=spec)