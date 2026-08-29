# structured append-only event logging for UAV-CI runs

from datetime import timedelta
import os
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from uav_ci.domain.enums import LogLevel
from uav_ci.domain.scenario import Identifier
from uav_ci.runtime.run_directory import RunDirectory


LogAttributeValue = (
    StrictBool
    | StrictInt
    | StrictFloat
    | StrictStr
    | None
)


class LogAttribute(BaseModel):
    # one immutable JSON-compatible event attribute

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    key: Identifier
    value: LogAttributeValue


# define the structured event
class StructuredEvent(BaseModel):
    # one timestamped even t in a UAV-CI run

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal[1] = 1
    timestamp: AwareDatetime
    monotonic_ns: int = Field(
        ge=0,
        strict=True,
    )

    run_id: UUID
    scenario_id: Identifier

    level: LogLevel
    component: Identifier
    event: Identifier
    message: str = Field(min_length=1)

    attributes: tuple[LogAttribute, ...] = ()

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError(
                "event timestamp must use UTC"
            )

        attribute_keys = [
            attribute.key
            for attribute in self.attributes
        ]

        if len(attribute_keys) != len(
            set(attribute_keys)
        ):
            raise ValueError(
                "event attribute keys must be unique"
            )

        return self

# implement append-only persistance
def append_event(
    run_directory: RunDirectory,
    event: StructuredEvent,
) -> None:
    # append one JSON event to its matching run

    if event.run_id != run_directory.run_id:
        raise ValueError(
            "event run_id does not match run directory"
        )

    if event.scenario_id != run_directory.scenario_id:
        raise ValueError(
            "event scenario_id does not match "
            "run directory"
        )

    if event.timestamp < run_directory.started_at:
        raise ValueError(
            "event timestamp cannot precede run start"
        )

    encoded_line = (
        event.model_dump_json() + "\n"
    ).encode("utf-8")

    file_descriptor = os.open(
        run_directory.events_path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )

    try:
        remaining = memoryview(encoded_line)

        while remaining:
            bytes_written = os.write(
                file_descriptor,
                remaining,
            )

            if bytes_written == 0:
                raise OSError(
                    "event log write made no progress"
                )

            remaining = remaining[bytes_written:]

        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)