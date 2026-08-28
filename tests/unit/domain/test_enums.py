import pytest

from uav_ci.domain.enums import (
    AssertionLayer,
    CheckOutcome,
    ClockDomain,
    EvidenceSource,
    ResultStatus,
)

# protects json report outputs
def test_enum_values_use_external_report_format() -> None:
    assert ResultStatus.PASS.value == "pass"
    assert AssertionLayer.ACTIVATION.value == "activation"
    assert CheckOutcome.NOT_EVALUATED.value == "not_evaluated"
    assert EvidenceSource.ULOG.value == "ulog"
    assert ClockDomain.PX4_BOOT.value == "px4_boot"

# protects json report inputs (YAML or JSON)
def test_enums_can_be_created_from_external_strings() -> None:
    assert ResultStatus("invalid") is ResultStatus.INVALID
    assert AssertionLayer("response") is AssertionLayer.RESPONSE

# verifies that unsupported enum values are rejected
def test_unkown_enum_value_is_rejuected() -> None:
    with pytest.raises(ValueError):
        ResultStatus("successful")