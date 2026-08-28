'''
proves that:
- nested evidence is validated automatically
- external strings become enums
- passed and failed assertions require evidence
- errors may exist without evidence
- unknown fields are rejected
- results are immutable
'''

import pytest
from pydantic import ValidationError

from uav_ci.domain.enums import AssertionLayer, CheckOutcome
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.result import AssertionResult


def valid_assertion_result_data() -> dict[str, object]:
    return {
        "assertion_id": "gnss_updates_stopped",
        "layer": "activation",
        "outcome": "passed",
        "message": "GNSS updates stopped after fault injection.",
        "evidence": [
            {
                "source": "telemetry",
                "clock_domain": "px4_boot",
                "timestamp_us": 18_420_000,
                "signal": "vehicle_gps_position.fix_type",
                "artifact_path": "telemetry/events.jsonl",
                "description": (
                    "GNSS fix type dropped below a valid 3D fix."
                ),
            }
        ],
    }


def test_valid_external_data_creates_assertion_result() -> None:
    result = AssertionResult.model_validate(
        valid_assertion_result_data()
    )

    assert result.layer is AssertionLayer.ACTIVATION
    assert result.outcome is CheckOutcome.PASSED
    assert isinstance(result.evidence, tuple)
    assert isinstance(result.evidence[0], EvidenceRef)


def test_evaluated_outcomes_without_evidence_are_rejected() -> None:
    for outcome in ("passed", "failed"):
        data = valid_assertion_result_data()
        data["outcome"] = outcome
        data["evidence"] = []

        with pytest.raises(ValidationError):
            AssertionResult.model_validate(data)


def test_error_outcome_can_exist_without_evidence() -> None:
    data = valid_assertion_result_data()
    data["outcome"] = "error"
    data["message"] = "ULog parser could not read the required topic."
    data["evidence"] = []

    result = AssertionResult.model_validate(data)

    assert result.outcome is CheckOutcome.ERROR
    assert result.evidence == ()


def test_unknown_field_is_rejected() -> None:
    data = valid_assertion_result_data()
    data["assertion_name"] = "Unexpected duplicate name"

    with pytest.raises(ValidationError):
        AssertionResult.model_validate(data)


def test_assertion_result_is_immutable() -> None:
    result = AssertionResult.model_validate(
        valid_assertion_result_data()
    )

    with pytest.raises(ValidationError):
        result.message = "Changed after evaluation"