'''
proves that an evidence reference:
- accepts valid external data
- converts strings into enums and paths
- rejects bad timestamps
- rejects unknown fields
- rejects unsafe artifact paths
- cannot be changed after creation
'''

from pathlib import Path
import pytest
from pydantic import ValidationError
from uav_ci.domain.enums import ClockDomain, EvidenceSource
from uav_ci.domain.evidence import EvidenceRef


def valid_evidence_data() -> dict[str, object]:
    return {
        "source": "telemetry",
        "clock_domain": "px4_boot",
        "timestamp_us": 18_420_000,
        "signal": "vehicle_gps_position.fix_type",
        "artifact_path": "telemetry/events.jsonl",
        "description": "GNSS fix type dropped below a valid 3D fix.",
    }


def test_valid_external_data_creates_evidence_reference() -> None:
    evidence = EvidenceRef.model_validate(valid_evidence_data())

    assert evidence.source is EvidenceSource.TELEMETRY
    assert evidence.clock_domain is ClockDomain.PX4_BOOT
    assert evidence.timestamp_us == 18_420_000
    assert evidence.artifact_path == Path("telemetry/events.jsonl")


def test_negative_timestamp_is_rejected() -> None:
    data = valid_evidence_data()
    data["timestamp_us"] = -1

    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(data)


def test_unknown_field_is_rejected() -> None:
    data = valid_evidence_data()
    data["unexpected_field"] = "unexpected value"

    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(data)


def test_unsafe_artifact_paths_are_rejected() -> None:
    for unsafe_path in (
        "/tmp/events.jsonl",
        "../events.jsonl",
        "telemetry/../../events.jsonl",
        "",
    ):
        data = valid_evidence_data()
        data["artifact_path"] = unsafe_path

        with pytest.raises(ValidationError):
            EvidenceRef.model_validate(data)


def test_evidence_reference_is_immutable() -> None:
    evidence = EvidenceRef.model_validate(valid_evidence_data())

    with pytest.raises(ValidationError):
        evidence.description = "Changed after creation"