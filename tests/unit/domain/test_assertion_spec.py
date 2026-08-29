# test scneario.py assertion spec functionality

import pytest
from pydantic import ValidationError

from uav_ci.domain.enums import (
    AssertionLayer,
    ComparisonOperator,
    EvidenceSource,
)
from uav_ci.domain.scenario import AssertionSpec


def valid_numeric_assertion_data() -> dict[str, object]:
    return {
        "assertion_id": "maximum_tilt_bounded",
        "layer": "outcome",
        "source": "ulog",
        "signal": "vehicle_attitude.maximum_tilt_deg",
        "operator": "less_than_or_equal",
        "expected": 35.0,
        "within_s": 10,
        "tolerance": 0.1,
        "description": "Maximum tilt remains within the limit.",
    }


def test_valid_numeric_assertion_is_parsed() -> None:
    assertion = AssertionSpec.model_validate(
        valid_numeric_assertion_data()
    )

    assert assertion.layer is AssertionLayer.OUTCOME
    assert assertion.source is EvidenceSource.ULOG
    assert (
        assertion.operator
        is ComparisonOperator.LESS_THAN_OR_EQUAL
    )
    assert assertion.expected == 35.0


def test_exists_assertion_does_not_require_expected() -> None:
    assertion = AssertionSpec.model_validate(
        {
            "assertion_id": "arm_command_observed",
            "layer": "activation",
            "source": "command",
            "signal": "mavsdk.action.arm",
            "operator": "exists",
            "description": "The unsafe arm command was submitted.",
        }
    )

    assert assertion.operator is ComparisonOperator.EXISTS
    assert assertion.expected is None


def test_comparison_assertion_requires_expected() -> None:
    data = valid_numeric_assertion_data()
    data.pop("expected")

    with pytest.raises(ValidationError):
        AssertionSpec.model_validate(data)


def test_exists_assertion_rejects_expected_and_tolerance() -> None:
    invalid_fields = (
        {
            "expected": True,
        },
        {
            "tolerance": 0.1,
        },
    )

    for fields in invalid_fields:
        data = {
            "assertion_id": "arm_command_observed",
            "layer": "activation",
            "source": "command",
            "signal": "mavsdk.action.arm",
            "operator": "exists",
            "description": "The unsafe arm command was submitted.",
            **fields,
        }

        with pytest.raises(ValidationError):
            AssertionSpec.model_validate(data)


def test_invalid_timing_and_tolerance_are_rejected() -> None:
    invalid_values = (
        {
            "within_s": 0,
        },
        {
            "within_s": -1,
        },
        {
            "tolerance": -0.1,
        },
    )

    for invalid_value in invalid_values:
        data = valid_numeric_assertion_data()
        data.update(invalid_value)

        with pytest.raises(ValidationError):
            AssertionSpec.model_validate(data)


def test_tolerance_requires_numeric_expected_value() -> None:
    data = valid_numeric_assertion_data()
    data["signal"] = "vehicle_status.nav_state"
    data["operator"] = "equal"
    data["expected"] = "land"
    data["tolerance"] = 0.1

    with pytest.raises(ValidationError):
        AssertionSpec.model_validate(data)


def test_unknown_comparison_operator_is_rejected() -> None:
    data = valid_numeric_assertion_data()
    data["operator"] = "approximately"

    with pytest.raises(ValidationError):
        AssertionSpec.model_validate(data)