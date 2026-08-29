# tests for structured append-only run logging

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from uav_ci.runtime import (
    LogAttribute,
    StructuredEvent,
    append_event,
    create_run_directory,
)


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
OTHER_RUN_ID = UUID(
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
)
STARTED_AT = datetime(
    2026,
    8,
    29,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_test_run(tmp_path: Path):
    return create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )


def event_data() -> dict[str, object]:
    return {
        "timestamp": (
            STARTED_AT + timedelta(seconds=1)
        ),
        "monotonic_ns": 1_000_000_000,
        "run_id": RUN_ID,
        "scenario_id": "baseline_mission",
        "level": "info",
        "component": "runtime",
        "event": "run_started",
        "message": "The UAV-CI run started.",
        "attributes": [
            {
                "key": "repetition_index",
                "value": 1,
            },
        ],
    }


def test_event_is_appended_as_json_line(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    event = StructuredEvent.model_validate(
        event_data()
    )

    append_event(run_directory, event)

    lines = (
        run_directory.events_path.read_text(
            encoding="utf-8"
        ).splitlines()
    )

    assert len(lines) == 1

    restored = StructuredEvent.model_validate(
        json.loads(lines[0])
    )

    assert restored == event


def test_multiple_events_preserve_order(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)

    first = StructuredEvent.model_validate(
        event_data()
    )
    second = first.model_copy(
        update={
            "timestamp": (
                first.timestamp
                + timedelta(seconds=1)
            ),
            "monotonic_ns": 2_000_000_000,
            "event": "preflight_completed",
            "message": "Environment preflight passed.",
        }
    )

    append_event(run_directory, first)
    append_event(run_directory, second)

    lines = (
        run_directory.events_path.read_text(
            encoding="utf-8"
        ).splitlines()
    )
    events = [
        json.loads(line)["event"]
        for line in lines
    ]

    assert events == [
        "run_started",
        "preflight_completed",
    ]


def test_event_identity_must_match_run(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    valid_event = StructuredEvent.model_validate(
        event_data()
    )

    invalid_events = (
        valid_event.model_copy(
            update={
                "run_id": OTHER_RUN_ID,
            }
        ),
        valid_event.model_copy(
            update={
                "scenario_id": "another_scenario",
            }
        ),
        valid_event.model_copy(
            update={
                "timestamp": (
                    STARTED_AT
                    - timedelta(seconds=1)
                ),
            }
        ),
    )

    for invalid_event in invalid_events:
        with pytest.raises(ValueError):
            append_event(
                run_directory,
                invalid_event,
            )

    assert not run_directory.events_path.exists()


def test_event_timestamp_must_use_utc() -> None:
    invalid_timestamps = (
        datetime(2026, 8, 29, 12, 0, 0),
        datetime(
            2026,
            8,
            29,
            12,
            0,
            0,
            tzinfo=timezone(
                timedelta(hours=-5)
            ),
        ),
    )

    for timestamp in invalid_timestamps:
        data = event_data()
        data["timestamp"] = timestamp

        with pytest.raises(ValidationError):
            StructuredEvent.model_validate(data)


def test_duplicate_attribute_keys_are_rejected() -> None:
    data = event_data()
    data["attributes"] = [
        {
            "key": "process_id",
            "value": 123,
        },
        {
            "key": "process_id",
            "value": 456,
        },
    ]

    with pytest.raises(ValidationError):
        StructuredEvent.model_validate(data)


def test_non_json_attribute_value_is_rejected() -> None:
    data = event_data()
    data["attributes"] = [
        {
            "key": "unsupported_value",
            "value": [
                "nested",
                "list",
            ],
        },
    ]

    with pytest.raises(ValidationError):
        StructuredEvent.model_validate(data)


def test_event_and_attributes_are_immutable() -> None:
    event = StructuredEvent.model_validate(
        event_data()
    )

    with pytest.raises(ValidationError):
        event.message = "Changed"

    with pytest.raises(ValidationError):
        event.attributes[0].value = 2

    assert isinstance(
        event.attributes[0],
        LogAttribute,
    )