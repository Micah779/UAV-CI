'''
these tests prove:
- nested dictionaries become typed models
- status is computed and serialized
- callers cannot provide a fake status
- timestamps are ordered and UTC
- errors and skipped contexts cannot conflict
- early skipped/error runs may have no assertions
- completed results are immutable
'''

import pytest
from pydantic import ValidationError

from uav_ci.domain.enums import ResultStatus
from uav_ci.domain.result import RunResult


def evidence_data() -> dict[str, object]:
    return {
        "source": "telemetry",
        "clock_domain": "px4_boot",
        "timestamp_us": 18_420_000,
        "signal": "test.signal",
        "artifact_path": "telemetry/events.jsonl",
        "description": "Evidence recorded during the run.",
    }


def assertion_data(
    assertion_id: str,
    layer: str,
) -> dict[str, object]:
    return {
        "assertion_id": assertion_id,
        "layer": layer,
        "outcome": "passed",
        "message": f"{assertion_id} passed.",
        "evidence": [evidence_data()],
    }


def valid_run_data() -> dict[str, object]:
    return {
        "run_id": "12345678-1234-5678-1234-567812345678",
        "scenario_id": "gnss_loss",
        "scenario_hash": "a" * 64,
        "requires_activation": True,
        "started_at": "2026-08-28T12:00:00Z",
        "finished_at": "2026-08-28T12:01:00Z",
        "assertions": [
            assertion_data(
                "vehicle_ready",
                "precondition",
            ),
            assertion_data(
                "gnss_updates_stopped",
                "activation",
            ),
            assertion_data(
                "failsafe_selected",
                "response",
            ),
            assertion_data(
                "vehicle_landed",
                "outcome",
            ),
        ],
    }


def test_valid_run_computes_and_serializes_status() -> None:
    run = RunResult.model_validate(valid_run_data())

    assert run.status is ResultStatus.PASS
    assert len(run.assertions) == 4

    serialized = run.model_dump(mode="json")

    assert serialized["status"] == "pass"
    assert serialized["scenario_id"] == "gnss_loss"


def test_caller_cannot_supply_status() -> None:
    data = valid_run_data()
    data["status"] = "pass"

    with pytest.raises(ValidationError):
        RunResult.model_validate(data)


def test_invalid_run_timestamps_are_rejected() -> None:
    invalid_times = (
        (
            "started_at",
            "2026-08-28T07:00:00-05:00",
        ),
        (
            "finished_at",
            "2026-08-28T11:59:59Z",
        ),
    )

    for field_name, value in invalid_times:
        data = valid_run_data()
        data[field_name] = value

        with pytest.raises(ValidationError):
            RunResult.model_validate(data)


def test_run_cannot_be_error_and_skipped() -> None:
    data = valid_run_data()
    data["harness_error"] = "ULog parser failed."
    data["skipped_reason"] = "Environment unavailable."

    with pytest.raises(ValidationError):
        RunResult.model_validate(data)


def test_skipped_run_can_have_no_assertions() -> None:
    data = valid_run_data()
    data["assertions"] = []
    data["skipped_reason"] = "Environment profile unavailable."

    run = RunResult.model_validate(data)

    assert run.status is ResultStatus.SKIPPED


def test_harness_error_can_have_no_assertions() -> None:
    data = valid_run_data()
    data["assertions"] = []
    data["harness_error"] = "PX4 process exited unexpectedly."

    run = RunResult.model_validate(data)

    assert run.status is ResultStatus.ERROR


def test_run_result_is_immutable() -> None:
    run = RunResult.model_validate(valid_run_data())

    with pytest.raises(ValidationError):
        run.scenario_id = "changed_scenario"