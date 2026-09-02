# offline activation assessment for the pinned uniform-wind profile.

from collections.abc import Sequence
from dataclasses import dataclass
import math

from uav_ci.domain.scenario import WindStimulusSpec
from uav_ci.faults.wind_command import WindCommand
from uav_ci.faults.wind_observer import RecordedWindObservation
from uav_ci.faults.wind_state import WindStateObservation


BASELINE_MAX_AGE_NS = 1_000_000_000
DIRECTION_TOLERANCE_DEG = 10.0
VERTICAL_TOLERANCE_M_S = 0.1
MAX_SPEED_RATIO = 1.05
REQUIRED_SAMPLES = 2


@dataclass(frozen=True, slots=True)
class WindActivationAssessment:
    activated: bool
    reason: str
    supporting_samples: tuple[RecordedWindObservation, ...] = ()


def _identity(sample: RecordedWindObservation) -> tuple[int, ...]:
    state = sample.observation
    return (
        state.world_entity_id,
        state.wind_entity_id,
        state.model_entity_id,
        state.link_entity_id,
    )


def _validate_sample(sample: RecordedWindObservation) -> None:
    state = sample.observation
    times = (
        sample.request_started_monotonic_ns,
        sample.request_finished_monotonic_ns,
        state.simulation_time_ns,
        state.iterations,
    )

    if any(type(value) is not int or value < 0 for value in times):
        raise ValueError(
            "sample times and iterations must be nonnegative integers"
        )

    if (
        sample.request_finished_monotonic_ns
        < sample.request_started_monotonic_ns
    ):
        raise ValueError("sample request timing is reversed")

    if any(
        type(value) is not int or value <= 0
        for value in _identity(sample)
    ):
        raise ValueError("sample entity IDs must be positive integers")

    if (
        type(state.paused) is not bool
        or type(state.link_wind_enabled) is not bool
    ):
        raise ValueError("sample state flags must be booleans")

    for vector in (
        state.wind_velocity_world_m_s,
        state.wind_seed_world_m_s,
    ):
        if len(vector) != 3 or any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError(
                "sample wind vectors must contain three finite numbers"
            )

        if not math.isfinite(math.hypot(*vector)):
            raise ValueError("sample wind magnitude overflow")


def _matches_request(
    state: WindStateObservation,
    request: WindCommand,
    stimulus: WindStimulusSpec,
) -> bool:
    expected = (
        request.x_m_s,
        request.y_m_s,
        request.z_m_s,
    )

    seed_matches = all(
        math.isclose(
            actual,
            target,
            rel_tol=1e-5,
            abs_tol=1e-6,
        )
        for actual, target in zip(
            state.wind_seed_world_m_s,
            expected,
            strict=True,
        )
    )

    x, y, z = state.wind_velocity_world_m_s
    horizontal_speed = math.hypot(x, y)

    if horizontal_speed == 0:
        return False

    direction = math.degrees(math.atan2(y, x))
    direction_error = abs(
        (
            direction
            - stimulus.direction_from_world_x_deg
            + 180
        ) % 360 - 180
    )

    return (
        seed_matches
        and horizontal_speed >= stimulus.minimum_proven_speed_m_s
        and state.wind_speed_m_s / stimulus.speed_m_s <= MAX_SPEED_RATIO
        and direction_error <= DIRECTION_TOLERANCE_DEG
        and abs(z) <= VERTICAL_TOLERANCE_M_S
    )


def evaluate_wind_activation(
    stimulus: WindStimulusSpec,
    baseline: RecordedWindObservation,
    samples: Sequence[RecordedWindObservation],
    *,
    command_started_monotonic_ns: int,
    command_finished_monotonic_ns: int,
) -> WindActivationAssessment:
    # assess trusted observer records in collection order, without I/O.

    for value in (
        command_started_monotonic_ns,
        command_finished_monotonic_ns,
    ):
        if type(value) is not int or value < 0:
            raise ValueError(
                "command timestamps must be nonnegative integers"
            )

    if command_finished_monotonic_ns < command_started_monotonic_ns:
        raise ValueError("command timing is reversed")

    if not math.isfinite(stimulus.minimum_proven_speed_m_s):
        raise ValueError("activation threshold must be finite")

    request = WindCommand.from_stimulus(stimulus)
    _validate_sample(baseline)
    base = baseline.observation

    deadline = (
        command_started_monotonic_ns
        + stimulus.activation_timeout_s * 1_000_000_000
    )

    if baseline.request_finished_monotonic_ns > command_started_monotonic_ns:
        return WindActivationAssessment(
            False,
            "baseline overlaps the command",
        )

    baseline_age = (
        command_started_monotonic_ns
        - baseline.request_finished_monotonic_ns
    )

    if baseline_age > BASELINE_MAX_AGE_NS:
        return WindActivationAssessment(
            False,
            "baseline is too old",
        )

    if base.paused or not base.link_wind_enabled:
        return WindActivationAssessment(
            False,
            "baseline is paused or link wind is disabled",
        )

    calm_limit = min(
        1e-6,
        float(stimulus.minimum_proven_speed_m_s) / 10,
    )

    if (
        base.wind_speed_m_s > calm_limit
        or math.hypot(*base.wind_seed_world_m_s) > calm_limit
    ):
        return WindActivationAssessment(
            False,
            "baseline does not show calm wind and zero seed",
        )

    if command_finished_monotonic_ns > deadline:
        return WindActivationAssessment(
            False,
            "command consumed the activation window",
        )

    previous = baseline
    qualifying: list[RecordedWindObservation] = []

    for sample in samples:
        _validate_sample(sample)
        state = sample.observation

        if sample.request_started_monotonic_ns < command_finished_monotonic_ns:
            return WindActivationAssessment(
                False,
                "observation overlaps the command",
            )

        if (
            sample.request_started_monotonic_ns
            < previous.request_finished_monotonic_ns
        ):
            return WindActivationAssessment(
                False,
                "observations are out of order or overlap",
            )

        if sample.request_finished_monotonic_ns > deadline:
            return WindActivationAssessment(
                False,
                "observation missed the activation deadline",
            )

        if _identity(sample) != _identity(baseline):
            return WindActivationAssessment(
                False,
                "simulator entity identity changed",
            )

        if (
            state.simulation_time_ns
            <= previous.observation.simulation_time_ns
            or state.iterations <= previous.observation.iterations
        ):
            return WindActivationAssessment(
                False,
                "simulation time or iterations did not advance",
            )

        if state.paused or not state.link_wind_enabled:
            return WindActivationAssessment(
                False,
                "observation is paused or link wind is disabled",
            )

        previous = sample

        if _matches_request(state, request, stimulus):
            qualifying.append(sample)
        else:
            qualifying.clear()

        if len(qualifying) == REQUIRED_SAMPLES:
            return WindActivationAssessment(
                activated=True,
                reason=(
                    "two consecutive observations demonstrate "
                    "the configured wind-state activation"
                ),
                supporting_samples=(baseline, *qualifying),
            )

    return WindActivationAssessment(
        False,
        "not enough consecutive observations meet the wind activation criteria",
    )