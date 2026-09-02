# decode full Gazebo 8 state snapshots; never classify activation.

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import math
import re

from google.protobuf import descriptor_pb2, message_factory, text_format
from google.protobuf.message import DecodeError


MASK_64 = (1 << 64) - 1
MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024
NUMBER = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)


class WindStateDecodeError(ValueError):
    # the snapshot cannot support a trustworthy wind observation.
    pass

# data we keep
@dataclass(frozen=True, slots=True)
class WindStateObservation:
    simulation_time_ns: int
    iterations: int
    paused: bool
    world_entity_id: int
    wind_entity_id: int
    model_entity_id: int
    link_entity_id: int
    wind_velocity_world_m_s: tuple[float, float, float]
    wind_seed_world_m_s: tuple[float, float, float]
    link_wind_enabled: bool

    @property
    def wind_speed_m_s(self) -> float:
        return math.hypot(*self.wind_velocity_world_m_s)

# loads the boundled schema once
@lru_cache(maxsize=1)
def _state_message_class():
    try:
        schema = descriptor_pb2.FileDescriptorSet.FromString(
            files(__package__).joinpath("data/gazebo_state.desc").read_bytes()
        )

        # Preserve map entries as lists so duplicate keys remain detectable.
        for file in schema.file:
            for message in file.message_type:
                for nested in message.nested_type:
                    if nested.options.map_entry:
                        nested.options.map_entry = False

        return message_factory.GetMessages(schema.file)[
            "gz.msgs.SerializedStepMap"
        ]
    except (OSError, DecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("could not load bundled Gazebo state schema") from exc


def _component_id(name: str) -> int:
    # Gazebo's registered component names use 64-bit FNV-1a.
    value = 0xCBF29CE484222325
    for byte in ("gz_sim_components." + name).encode("ascii"):
        value = ((value ^ byte) * 0x100000001B3) & MASK_64
    return value


def _component(components: dict[int, bytes], name: str) -> bytes:
    try:
        return components[_component_id(name)]
    except KeyError as exc:
        raise WindStateDecodeError(f"missing component: {name}") from exc


def _parent(components: dict[int, bytes]) -> int:
    raw = _component(components, "ParentEntity")
    if re.fullmatch(rb"[1-9][0-9]*", raw) is None:
        raise WindStateDecodeError("invalid ParentEntity")
    value = int(raw)
    if value > MASK_64:
        raise WindStateDecodeError("ParentEntity exceeds uint64")
    return value


def _tagged(components: dict[int, bytes], tag: str) -> bool:
    key = _component_id(tag)
    if key not in components:
        return False
    if components[key] != b"-":
        raise WindStateDecodeError(f"invalid component tag: {tag}")
    return True


def _unique(candidates: list[int], description: str) -> int:
    if len(candidates) != 1:
        raise WindStateDecodeError(
            f"expected exactly one {description}; found {len(candidates)}"
        )
    return candidates[0]


def _named_entity(entities, *, tag, name, parent=None):
    candidates = []
    for entity_id, components in entities.items():
        if not _tagged(components, tag):
            continue
        if _component(components, "Name") != name.encode("utf-8"):
            continue
        if parent is not None and _parent(components) != parent:
            continue
        candidates.append(entity_id)
    return _unique(candidates, f"{tag} named {name}")


def _vector(raw: bytes, name: str) -> tuple[float, float, float]:
    try:
        parts = raw.decode("ascii").split()
        if len(parts) != 3 or any(NUMBER.fullmatch(p) is None for p in parts):
            raise ValueError("expected three decimal numbers")
        vector = tuple(float(part) for part in parts)
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("nonfinite vector")
        if not math.isfinite(math.hypot(*vector)):
            raise ValueError("vector magnitude overflow")
        return vector[0], vector[1], vector[2]
    except (UnicodeError, ValueError) as exc:
        raise WindStateDecodeError(f"invalid {name} vector") from exc


def _index_entities(message) -> dict[int, dict[int, bytes]]:
    entities = {}
    for entry in message.state.entities:
        entity = entry.value
        if entry.key == 0 or entry.key != entity.id:
            raise WindStateDecodeError("entity key/id mismatch")
        if entry.key in entities:
            raise WindStateDecodeError("duplicate entity id")
        if entity.remove:
            raise WindStateDecodeError("removed entity in full snapshot")

        components = {}
        for item in entity.components:
            component = item.value
            # Map keys are int64; component type IDs are uint64.
            if component.type == 0 or (item.key & MASK_64) != component.type:
                raise WindStateDecodeError("component key/type mismatch")
            if component.type in components:
                raise WindStateDecodeError("duplicate component type")
            if component.remove:
                raise WindStateDecodeError("removed component in full snapshot")
            components[component.type] = bytes(component.component)

        entities[entry.key] = components
    return entities

# combines those helpsers into the public entry point
def decode_wind_state(contents: str) -> WindStateObservation:
    # decode a /world/default/state service response, not a topic delta.
    if not contents.strip():
        raise WindStateDecodeError("empty state snapshot")
    if len(contents.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise WindStateDecodeError("state snapshot exceeds size limit")

    message = _state_message_class()()
    try:
        text_format.Parse(contents, message)
    except text_format.ParseError as exc:
        raise WindStateDecodeError("malformed Gazebo state protobuf") from exc

    if not message.HasField("stats") or not message.HasField("state"):
        raise WindStateDecodeError("snapshot requires stats and state")
    if not message.stats.HasField("sim_time"):
        raise WindStateDecodeError("snapshot requires simulation time")

    stamp = message.stats.sim_time
    if stamp.sec < 0 or not 0 <= stamp.nsec < 1_000_000_000:
        raise WindStateDecodeError("invalid simulation time")

    entities = _index_entities(message)
    world = _named_entity(entities, tag="World", name="default")
    model = _named_entity(
        entities, tag="Model", name="x500_0", parent=world
    )
    link = _named_entity(
        entities, tag="Link", name="base_link", parent=model
    )
    wind = _unique(
        [
            entity_id
            for entity_id, components in entities.items()
            if _tagged(components, "Wind") and _parent(components) == world
        ],
        "Wind entity in default world",
    )

    enabled = _component(entities[link], "WindMode")
    if enabled not in (b"0", b"1"):
        raise WindStateDecodeError("invalid link WindMode")

    return WindStateObservation(
        simulation_time_ns=stamp.sec * 1_000_000_000 + stamp.nsec,
        iterations=message.stats.iterations,
        paused=message.stats.paused,
        world_entity_id=world,
        wind_entity_id=wind,
        model_entity_id=model,
        link_entity_id=link,
        wind_velocity_world_m_s=_vector(
            _component(entities[wind], "WorldLinearVelocity"),
            "WorldLinearVelocity",
        ),
        wind_seed_world_m_s=_vector(
            _component(entities[wind], "WorldLinearVelocitySeed"),
            "WorldLinearVelocitySeed",
        ),
        link_wind_enabled=enabled == b"1",
    )