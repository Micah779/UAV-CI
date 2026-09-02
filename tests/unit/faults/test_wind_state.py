# offline decoder tests using real, no-wind Gazebo captures.

from dataclasses import FrozenInstanceError
from pathlib import Path

from google.protobuf import text_format
import pytest

from uav_ci.faults import wind_state as module
from uav_ci.faults.wind_state import WindStateDecodeError, decode_wind_state


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gazebo"


def snapshot(index=1):
    return (FIXTURES / f"gazebo-state-{index}.txt").read_text(encoding="utf-8")


def message():
    return text_format.Parse(snapshot(), module._state_message_class()())


def decode(message):
    return decode_wind_state(text_format.MessageToString(message))


def entity(message, entity_id):
    return next(row for row in message.state.entities if row.key == entity_id)


def component(message, entity_id, name):
    return next(
        row for row in entity(message, entity_id).value.components
        if row.value.type == module._component_id(name)
    )


@pytest.mark.parametrize(
    ("index", "expected_time", "expected_iterations"),
    [(1, 9_764_000_000, 2441), (2, 10_576_000_000, 2644)],
)
def test_real_snapshots(index, expected_time, expected_iterations):
    observed = decode_wind_state(snapshot(index))
    assert observed.simulation_time_ns == expected_time
    assert observed.iterations == expected_iterations
    assert observed.paused is False
    assert observed.world_entity_id == 1
    assert observed.wind_entity_id == 3
    assert observed.model_entity_id == 10
    assert observed.link_entity_id == 11
    assert observed.link_wind_enabled is True
    assert observed.wind_velocity_world_m_s == (0.0, 0.0, 0.0)
    assert observed.wind_seed_world_m_s == (0.0, 0.0, 0.0)
    assert observed.wind_speed_m_s == 0.0
    assert not hasattr(observed, "activated")


def test_simulation_time_advances_between_real_snapshots():
    first = decode_wind_state(snapshot(1))
    second = decode_wind_state(snapshot(2))
    assert second.simulation_time_ns - first.simulation_time_ns == 812_000_000
    assert second.iterations > first.iterations


def test_requested_seed_is_not_actual_wind():
    data = message()
    component(data, 3, "WorldLinearVelocitySeed").value.component = b"0 5 0"
    observed = decode(data)
    assert observed.wind_seed_world_m_s == (0.0, 5.0, 0.0)
    assert observed.wind_speed_m_s == 0.0


def test_nonzero_actual_wind_and_signed_component_keys():
    data = message()
    velocity = component(data, 3, "WorldLinearVelocity")
    assert any(row.key < 0 for row in entity(data, 1).value.components)
    velocity.value.component = b"-3 4 0"
    observed = decode(data)
    assert observed.wind_velocity_world_m_s == (-3.0, 4.0, 0.0)
    assert observed.wind_speed_m_s == 5.0


def test_disabled_link_and_paused_world_remain_observable():
    data = message()
    data.stats.paused = True
    component(data, 11, "WindMode").value.component = b"0"
    observed = decode(data)
    assert observed.paused is True
    assert observed.link_wind_enabled is False


def test_observation_is_immutable():
    observed = decode_wind_state(snapshot())
    with pytest.raises(FrozenInstanceError):
        observed.paused = True


@pytest.mark.parametrize(
    "contents",
    ["", "Service call failed", "stats {", "typo: 1"],
)
def test_empty_or_malformed_input(contents):
    with pytest.raises(WindStateDecodeError):
        decode_wind_state(contents)


@pytest.mark.parametrize("field", ["stats", "state", "sim_time"])
def test_missing_required_message(field):
    data = message()
    target = data.stats if field == "sim_time" else data
    target.ClearField(field)
    with pytest.raises(WindStateDecodeError):
        decode(data)


@pytest.mark.parametrize(
    ("seconds", "nanoseconds"),
    [(-1, 0), (0, -1), (0, 1_000_000_000)],
)
def test_invalid_simulation_time(seconds, nanoseconds):
    data = message()
    data.stats.sim_time.sec = seconds
    data.stats.sim_time.nsec = nanoseconds
    with pytest.raises(WindStateDecodeError, match="simulation time"):
        decode(data)


@pytest.mark.parametrize("entity_id", [1, 3, 10, 11])
def test_missing_or_ambiguous_required_entity(entity_id):
    data = message()
    row = entity(data, entity_id)
    duplicate = data.state.entities.add()
    duplicate.CopyFrom(row)
    duplicate.key = 999
    duplicate.value.id = 999
    with pytest.raises(WindStateDecodeError, match="exactly one"):
        decode(data)

    data = message()
    data.state.entities.remove(entity(data, entity_id))
    with pytest.raises(WindStateDecodeError, match="exactly one"):
        decode(data)


@pytest.mark.parametrize("entity_id", [3, 10, 11])
def test_required_entity_must_have_correct_parent(entity_id):
    data = message()
    component(data, entity_id, "ParentEntity").value.component = b"999"
    with pytest.raises(WindStateDecodeError, match="exactly one"):
        decode(data)


@pytest.mark.parametrize(
    "name",
    ["WorldLinearVelocity", "WorldLinearVelocitySeed"],
)
def test_missing_wind_vector(name):
    data = message()
    entity(data, 3).value.components.remove(component(data, 3, name))
    with pytest.raises(WindStateDecodeError, match="missing component"):
        decode(data)


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"1 2",
        b"1 2 3 4",
        b"nan 0 0",
        b"inf 0 0",
        b"1e999 0 0",
        b"1_0 0 0",
        b"\xff 0 0",
        b"1.7e308 1.7e308 0",
    ],
)
def test_invalid_wind_vector(value):
    data = message()
    component(data, 3, "WorldLinearVelocity").value.component = value
    with pytest.raises(WindStateDecodeError, match="vector"):
        decode(data)


def test_invalid_link_wind_mode():
    data = message()
    component(data, 11, "WindMode").value.component = b"true"
    with pytest.raises(WindStateDecodeError, match="WindMode"):
        decode(data)


def test_duplicate_map_keys_are_not_silently_overwritten():
    data = message()
    data.state.entities.add().CopyFrom(entity(data, 3))
    with pytest.raises(WindStateDecodeError, match="duplicate entity"):
        decode(data)

    data = message()
    duplicate = entity(data, 3).value.components.add()
    duplicate.CopyFrom(component(data, 3, "WorldLinearVelocity"))
    with pytest.raises(WindStateDecodeError, match="duplicate component"):
        decode(data)


def test_mismatched_ids_are_rejected():
    data = message()
    entity(data, 3).value.id = 999
    with pytest.raises(WindStateDecodeError, match="key/id"):
        decode(data)

    data = message()
    component(data, 3, "WorldLinearVelocity").key = 999
    with pytest.raises(WindStateDecodeError, match="key/type"):
        decode(data)


def test_tombstones_are_rejected():
    data = message()
    entity(data, 3).value.remove = True
    with pytest.raises(WindStateDecodeError, match="removed entity"):
        decode(data)

    data = message()
    component(data, 3, "WorldLinearVelocity").value.remove = True
    with pytest.raises(WindStateDecodeError, match="removed component"):
        decode(data)


def test_size_limit(monkeypatch):
    monkeypatch.setattr(module, "MAX_SNAPSHOT_BYTES", 10)
    with pytest.raises(WindStateDecodeError, match="size limit"):
        decode_wind_state(snapshot())


@pytest.mark.parametrize(
    "raw",
    [b"0", b"abc", b"18446744073709551616"],
)
def test_malformed_parent(raw):
    data = message()
    component(data, 11, "ParentEntity").value.component = raw
    with pytest.raises(WindStateDecodeError, match="ParentEntity"):
        decode(data)


def test_missing_link_wind_mode():
    data = message()
    entity(data, 11).value.components.remove(
        component(data, 11, "WindMode")
    )
    with pytest.raises(
        WindStateDecodeError,
        match="missing component: WindMode",
    ):
        decode(data)


def test_invalid_wind_tag():
    data = message()
    component(data, 3, "Wind").value.component = b"1"
    with pytest.raises(
        WindStateDecodeError,
        match="invalid component tag",
    ):
        decode(data)