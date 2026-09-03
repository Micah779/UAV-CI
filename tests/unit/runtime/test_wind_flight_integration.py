# wind flight orchestration uses fake vehicle and simulator owners

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.enums import ResultStatus
from uav_ci.faults.controller import (
    FaultActivationNotProven,
    FaultActivationResult,
)
from uav_ci.runtime import flight as module
from uav_ci.scenario import load_scenario
from uav_ci.vehicle import MissionExecutionResult


ROOT = Path(__file__).parents[3]
FINISH = datetime(
    2026,
    9,
    3,
    12,
    tzinfo=timezone.utc,
)


class Preconditions:
    passed = True
    observed_at = FINISH

    def model_dump_json(
        self,
        **options,
    ):
        return "{}"


def setup_run(
    tmp_path,
    monkeypatch,
    *,
    proven=True,
    failure=None,
):
    evidence = tmp_path / "evidence"
    logs = tmp_path / "logs"

    evidence.mkdir()
    logs.mkdir()

    directory = SimpleNamespace(
        root=tmp_path,
        vehicle_preconditions_path=(
            evidence
            / "vehicle_preconditions.json"
        ),
        mission_execution_path=(
            evidence
            / "mission_execution.json"
        ),
        land_detection_path=(
            evidence
            / "land_detection.json"
        ),
        result_path=tmp_path / "result.json",
    )

    prepared = SimpleNamespace(
        run_directory=directory,
        manifest=SimpleNamespace(
            scenario_id="wind_tracking",
            requires_activation=True,
        ),
        snapshots=SimpleNamespace(
            mission_path=(
                tmp_path / "mission.plan"
            ),
        ),
    )

    spec = load_scenario(
        ROOT / "scenarios/wind.yaml"
    ).scenario

    events = []

    activation = FaultActivationResult(
        fault_type="wind",
        activated=proven,
        evidence=(
            EvidenceRef(
                source="harness",
                clock_domain="host_monotonic",
                timestamp_us=100,
                signal=(
                    "wind_activation.assessment"
                ),
                artifact_path=Path(
                    "evidence/wind/activation.json"
                ),
                description=(
                    "synthetic assessment"
                ),
            ),
        ),
    )

    running = SimpleNamespace(
        vehicle=object(),
        process=SimpleNamespace(
            stdout_path=(
                logs / "px4.stdout.log"
            ),
        ),
        shutdown_returncode=None,
    )

    @asynccontextmanager
    async def environment(
        *args,
        **options,
    ):
        events.append("environment entered")

        try:
            yield running
        finally:
            running.shutdown_returncode = -15
            events.append("environment stopped")

    class Lifecycle:
        async def activate(self):
            events.append("wind requested")

        async def prove_activation(self):
            events.append("wind assessed")

            if failure == "activation":
                raise RuntimeError(
                    "activation infrastructure failed"
                )

            return activation

        def require_activation_proven(self):
            events.append("activation gate")

            if not activation.activated:
                raise FaultActivationNotProven(
                    "wind was not proven"
                )

            return activation

    @asynccontextmanager
    async def wind_controller(
        received_spec,
        root,
    ):
        assert received_spec == spec.stimulus
        assert root == tmp_path

        try:
            yield Lifecycle()
        finally:
            events.append("wind cleaned")

            if failure == "cleanup":
                raise RuntimeError(
                    "wind cleanup failed"
                )

    async def readiness(
        *args,
        **options,
    ):
        return Preconditions()

    async def mission(
        *args,
        on_airborne,
        **options,
    ):
        events.append("airborne")
        await on_airborne()

        if failure == "cancel":
            raise asyncio.CancelledError()

        events.append("mission completed")

        return MissionExecutionResult(
            mission_item_count=4,
            final_current=4,
            final_total=4,
            armed_observed=True,
            airborne_observed=True,
            landed_observed=True,
            disarmed_observed=True,
            elapsed_s=120,
        )

    def capture(
        *args,
        **options,
    ):
        assert running.shutdown_returncode == -15

        events.append("ulog captured")

        if failure == "capture":
            raise RuntimeError(
                "ULog capture failed"
            )

        return SimpleNamespace(
            path=logs / "flight.ulg"
        )

    def analyze(path):
        events.append("response analysis")

        # Flight writes the returned dataclass
        # as JSON.
        from uav_ci.analysis import (
            LandDetectionSummary,
        )

        return LandDetectionSummary(
            topic="vehicle_land_detected",
            instance=0,
            sample_count=100,
            first_timestamp_us=1,
            last_timestamp_us=100,
            initial_landed=True,
            airborne_observed=True,
            first_airborne_timestamp_us=10,
            final_landed=True,
            landing_transition_observed=True,
            landing_timestamp_us=90,
        )

    def evaluate(
        received_spec,
        manifest,
        **options,
    ):
        assert (
            options["activation"]
            is activation
        )

        events.append("wind evaluated")

        return SimpleNamespace(
            status=ResultStatus.PASS
        )

    def invalid(
        *args,
        **options,
    ):
        assert (
            options["activation"]
            is activation
        )

        events.append("invalid written")

    def error(
        *args,
        **options,
    ):
        events.append("error written")

    monkeypatch.setattr(
        module,
        "_load_snapshotted_scenario",
        lambda prepared_run: spec,
    )
    monkeypatch.setattr(
        module,
        "managed_environment",
        environment,
    )
    monkeypatch.setattr(
        module,
        "_wind_controller_context",
        wind_controller,
    )
    monkeypatch.setattr(
        module,
        "wait_for_vehicle_preconditions",
        readiness,
    )
    monkeypatch.setattr(
        module,
        "execute_mission",
        mission,
    )
    monkeypatch.setattr(
        module,
        "capture_px4_ulog",
        capture,
    )
    monkeypatch.setattr(
        module,
        "analyze_land_detection",
        analyze,
    )
    monkeypatch.setattr(
        module,
        "evaluate_wind",
        evaluate,
    )
    monkeypatch.setattr(
        module,
        "write_run_result",
        lambda *args: None,
    )
    monkeypatch.setattr(
        module,
        "write_invalid_activation_result",
        invalid,
    )
    monkeypatch.setattr(
        module,
        "write_harness_error_result",
        error,
    )

    return prepared, events, activation


def test_wind_lives_through_mission_and_analysis_follows_gate(
    tmp_path,
    monkeypatch,
):
    prepared, events, activation = setup_run(
        tmp_path,
        monkeypatch,
    )

    result = asyncio.run(
        module.run_flight_check(
            prepared,
            px4_repository=(
                tmp_path / "px4"
            ),
            clock=lambda: FINISH,
        )
    )

    assert result.activation is activation

    assert events == [
        "environment entered",
        "airborne",
        "wind requested",
        "wind assessed",
        "mission completed",
        "wind cleaned",
        "environment stopped",
        "ulog captured",
        "activation gate",
        "response analysis",
        "wind evaluated",
    ]


def test_unproven_wind_is_invalid_after_safe_completion(
    tmp_path,
    monkeypatch,
):
    prepared, events, _ = setup_run(
        tmp_path,
        monkeypatch,
        proven=False,
    )

    with pytest.raises(
        FaultActivationNotProven,
    ):
        asyncio.run(
            module.run_flight_check(
                prepared,
                px4_repository=(
                    tmp_path / "px4"
                ),
                clock=lambda: FINISH,
            )
        )

    assert "mission completed" in events
    assert "ulog captured" in events
    assert events[-1] == "invalid written"
    assert "response analysis" not in events
    assert "wind evaluated" not in events


@pytest.mark.parametrize(
    "failure",
    [
        "activation",
        "cleanup",
        "capture",
    ],
)
def test_infrastructure_errors_take_precedence(
    tmp_path,
    monkeypatch,
    failure,
):
    prepared, events, _ = setup_run(
        tmp_path,
        monkeypatch,
        proven=False,
        failure=failure,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            module.run_flight_check(
                prepared,
                px4_repository=(
                    tmp_path / "px4"
                ),
                clock=lambda: FINISH,
            )
        )

    assert "wind cleaned" in events
    assert "environment stopped" in events
    assert events[-1] == "error written"
    assert "invalid written" not in events
    assert "response analysis" not in events


def test_cancellation_still_retains_error_evidence(
    tmp_path,
    monkeypatch,
):
    prepared, events, _ = setup_run(
        tmp_path,
        monkeypatch,
        failure="cancel",
    )

    with pytest.raises(
        asyncio.CancelledError,
    ):
        asyncio.run(
            module.run_flight_check(
                prepared,
                px4_repository=(
                    tmp_path / "px4"
                ),
                clock=lambda: FINISH,
            )
        )

    assert "wind cleaned" in events
    assert "environment stopped" in events
    assert "ulog captured" in events
    assert events[-1] == "error written"