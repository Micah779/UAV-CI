# tests for immutable UAV-CI run manifests

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from uav_ci.domain.manifest import RunManifest


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
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
SCENARIO_HASH = "a" * 64
ENVIRONMENT_HASH = "b" * 64


def valid_manifest_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "scenario_id": "baseline_mission",
        "scenario_hash": SCENARIO_HASH,
        "environment_profile": "px4-gz-x500-v1",
        "requires_activation": False,
        "repetition_index": 1,
        "repetition_count": 1,
        "seed": 42,
        "started_at": STARTED_AT,
        "harness": {
            "uav_ci_version": "0.1.0",
            "python_version": "3.14.7",
            "platform": "macOS-arm64",
        },
        "environment_profile": "px4-gz-x500-v1",
        "environment_hash": ENVIRONMENT_HASH,
        "requires_activation": False,
    }


def test_valid_manifest_is_parsed() -> None:
    manifest = RunManifest.model_validate(
        valid_manifest_data()
    )

    assert manifest.run_id == RUN_ID
    assert manifest.scenario_id == "baseline_mission"
    assert manifest.scenario_hash == SCENARIO_HASH
    assert manifest.repetition_index == 1
    assert manifest.repetition_count == 1
    assert manifest.harness.uav_ci_version == "0.1.0"
    assert manifest.environment_hash == ENVIRONMENT_HASH


def test_invalid_repetition_bounds_are_rejected() -> None:
    invalid_repetitions = (
        {
            "repetition_index": 0,
            "repetition_count": 1,
        },
        {
            "repetition_index": 1,
            "repetition_count": 0,
        },
        {
            "repetition_index": 2,
            "repetition_count": 1,
        },
    )

    for repetition in invalid_repetitions:
        data = valid_manifest_data()
        data.update(repetition)

        with pytest.raises(ValidationError):
            RunManifest.model_validate(data)


def test_non_utc_started_at_is_rejected() -> None:
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
        data = valid_manifest_data()
        data["started_at"] = timestamp

        with pytest.raises(ValidationError):
            RunManifest.model_validate(data)


def test_invalid_scenario_hash_is_rejected() -> None:
    invalid_hashes = (
        "abc123",
        "A" * 64,
        "g" * 64,
        "a" * 63,
        "a" * 65,
    )

    for scenario_hash in invalid_hashes:
        data = valid_manifest_data()
        data["scenario_hash"] = scenario_hash

        with pytest.raises(ValidationError):
            RunManifest.model_validate(data)
            
def test_invalid_environment_hash_is_rejected() -> None:
    invalid_hashes = (
        "abc123",
        "B" * 64,
        "g" * 64,
        "b" * 63,
        "b" * 65,
    )

    for environment_hash in invalid_hashes:
        data = valid_manifest_data()
        data["environment_hash"] = environment_hash

        with pytest.raises(ValidationError):
            RunManifest.model_validate(data)

def test_unsupported_environment_is_rejected() -> None:
    data = valid_manifest_data()
    data["environment_profile"] = "px4-gz-iris-v1"

    with pytest.raises(ValidationError):
        RunManifest.model_validate(data)


def test_unknown_manifest_field_is_rejected() -> None:
    data = valid_manifest_data()
    data["status"] = "pass"

    with pytest.raises(ValidationError):
        RunManifest.model_validate(data)


def test_manifest_is_immutable() -> None:
    manifest = RunManifest.model_validate(
        valid_manifest_data()
    )

    with pytest.raises(ValidationError):
        manifest.repetition_index = 2