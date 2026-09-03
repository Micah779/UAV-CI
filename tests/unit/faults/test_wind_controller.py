# synthetic controller tests: no simulator, vehicle, or wind is contacted

import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from uav_ci.domain.scenario import WindStimulusSpec
from uav_ci.faults.controller import (
    FaultActivationNotProven,
    FaultController,
    FaultLifecycleError,
)
from uav_ci.faults.wind_command import CommandOutput, WindCommandError
from uav_ci.faults.wind_controller import (
    GazeboWindController,
    managed_wind_controller,
)
from uav_ci.faults import wind_controller as module
from uav_ci.faults.wind_observer import (
    RecordedWindObservation,
    WindObservationError,
    WindObservationTimeout,
)
from uav_ci.faults.wind_state import decode_wind_state


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures/gazebo/gazebo-state-1.txt"
)
DIAGNOSTIC = (
    "I0902 11:55:14.180964 6775763 ev_poll_posix.cc:593] "
    "FD from fork parent still in poll list:fd(13, generation: 1)\n"
)


def stimulus():
    return WindStimulusSpec(
        type="wind",
        speed_m_s=5,
        direction_from_world_x_deg=90,
        minimum_proven_speed_m_s=4.5,
        activation_timeout_s=5,
        activation_check_ids=("wind_reached_vehicle",),
    )


def read(root, name):
    return json.loads((root / "evidence/wind" / name).read_text())


class Rig:
    def __init__(self, root):
        self.root = root
        (root / "evidence").mkdir()
        self.now = 100_000_000_000
        self.state = decode_wind_state(FIXTURE.read_text())
        self.sequence = 0
        self.commands = []
        self.sessions = []
        self.closed = []
        self.baseline_changes = {}
        self.baseline_age_ns = 0
        self.speeds = [5, 5]
        self.observation_error = None
        self.command_error = None
        self.cleanup_error = None
        self.output = CommandOutput(0, "", "")

    def clock(self):
        return self.now

    async def runner(self, argv, *, timeout_s):
        self.commands.append(argv)
        self.now += 100_000_000
        error = (
            self.cleanup_error
            if "enable_wind: false" in argv[-1]
            else self.command_error
        )
        if error is not None:
            raise error
        return self.output

    async def observe(self, path, **options):
        path.mkdir()
        kind = path.name
        self.sessions.append((kind, options["timeout_s"]))
        try:
            if kind == "activation" and self.observation_error:
                raise self.observation_error
            speeds = [0] if kind == "baseline" else self.speeds
            for index, speed in enumerate(speeds, 1):
                started = self.now
                self.now += 100_000_000
                self.sequence += 1
                state = replace(
                    self.state,
                    simulation_time_ns=(
                        self.state.simulation_time_ns
                        + self.sequence * 100_000_000
                    ),
                    iterations=self.state.iterations + self.sequence,
                    wind_velocity_world_m_s=(0, speed, 0),
                    wind_seed_world_m_s=(0, 0 if kind == "baseline" else 5, 0),
                )
                if kind == "baseline":
                    state = replace(state, **self.baseline_changes)
                artifact = path / f"sample-{index:06d}.json"
                artifact.write_text(json.dumps({
                    "synthetic": True,
                    "observation": asdict(state),
                }))
                yield RecordedWindObservation(state, artifact, started, self.now)
        finally:
            self.closed.append(kind)
            if kind == "baseline":
                self.now += self.baseline_age_ns

    def managed(self):
        return managed_wind_controller(
            stimulus(), self.root,
            runner=self.runner, observer=self.observe, clock=self.clock,
        )


def test_proof_is_saved_and_cleanup_is_idempotent(tmp_path):
    rig = Rig(tmp_path)
    rig.output = CommandOutput(0, "", DIAGNOSTIC)

    async def exercise():
        async with rig.managed() as lifecycle:
            assert not rig.sessions  # prepare did not take an early baseline
            await lifecycle.activate()
            result = await lifecycle.prove_activation()
            assert lifecycle.require_activation_proven() == result
            assert result.activated is True
            ref = result.evidence[0]
            assert ref.source.value == "harness"
            assert ref.clock_domain.value == "host_monotonic"
            assert (tmp_path / ref.artifact_path).is_file()
        await lifecycle.cleanup()

    asyncio.run(exercise())
    assert len(rig.commands) == 2
    assert "enable_wind: false" in rig.commands[-1][-1]
    assert rig.closed == ["baseline", "activation"]
    decision = read(tmp_path, "activation.json")
    assert decision["activated"] is True
    assert len(decision["supporting_samples"]) == 3
    assert all((tmp_path / p).is_file() for p in decision["supporting_samples"])
    assert read(tmp_path, "command.json")["output"]["stderr"] == DIAGNOSTIC
    assert read(tmp_path, "cleanup-command.json")["restoration_proven"] is False


@pytest.mark.parametrize("speeds", [[], [5], [0, 0], [5, 4, 5]])
def test_unproven_activation_keeps_response_gate_closed(tmp_path, speeds):
    rig = Rig(tmp_path)
    rig.speeds = speeds

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            result = await lifecycle.prove_activation()
            assert result.activated is False
            with pytest.raises(FaultActivationNotProven):
                lifecycle.require_activation_proven()

    asyncio.run(exercise())
    assert read(tmp_path, "activation.json")["activated"] is False
    assert len(rig.commands) == 2


@pytest.mark.parametrize("changes", [
    {"paused": True}, {"link_wind_enabled": False},
    {"wind_velocity_world_m_s": (0, 5, 0)},
    {"wind_seed_world_m_s": (0, 5, 0)},
])
def test_bad_baseline_never_publishes(tmp_path, changes):
    rig = Rig(tmp_path)
    rig.baseline_changes = changes

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            assert not (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert rig.commands == []
    assert read(tmp_path, "activation.json")["command"] is None
    assert read(tmp_path, "cleanup-command.json")["command_attempted"] is False


def test_stale_baseline_never_publishes(tmp_path):
    rig = Rig(tmp_path)
    rig.baseline_age_ns = 1_000_000_001

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            assert not (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert rig.commands == []


def test_delay_before_proof_does_not_restart_budget(tmp_path):
    rig = Rig(tmp_path)

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            rig.now += 1_000_000_000
            assert (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert rig.sessions[1] == ("activation", pytest.approx(3.9))


def test_expired_window_never_starts_observer(tmp_path):
    rig = Rig(tmp_path)

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            rig.now += 5_000_000_000
            assert not (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert len(rig.sessions) == 1


def test_observation_timeout_is_unproven_not_vehicle_failure(tmp_path):
    rig = Rig(tmp_path)
    rig.observation_error = WindObservationTimeout("late")

    async def exercise():
        async with rig.managed() as lifecycle:
            await lifecycle.activate()
            assert not (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert "budget" in read(tmp_path, "activation.json")["reason"]


@pytest.mark.parametrize("error", [
    WindObservationError("bad data"), asyncio.CancelledError(),
])
def test_observer_errors_propagate_after_cleanup(tmp_path, error):
    rig = Rig(tmp_path)
    rig.observation_error = error

    async def exercise():
        with pytest.raises(type(error)):
            async with rig.managed() as lifecycle:
                await lifecycle.activate()
                await lifecycle.prove_activation()

    asyncio.run(exercise())
    assert len(rig.commands) == 2
    assert not (tmp_path / "evidence/wind/activation.json").exists()


@pytest.mark.parametrize("error", [
    WindCommandError("delivery unknown"), asyncio.CancelledError(),
])
def test_publication_failure_still_requests_disable(tmp_path, error):
    rig = Rig(tmp_path)
    rig.command_error = error

    async def exercise():
        with pytest.raises(type(error)):
            async with rig.managed() as lifecycle:
                await lifecycle.activate()

    asyncio.run(exercise())
    assert len(rig.commands) == 2
    record = read(tmp_path, "command.json")
    assert record["output"] is None
    assert record["error"]["type"] == type(error).__name__


def test_bad_publisher_diagnostics_are_retained(tmp_path):
    rig = Rig(tmp_path)
    rig.output = CommandOutput(0, "", "unexpected diagnostic")

    async def exercise():
        with pytest.raises(WindCommandError) as caught:
            async with rig.managed() as lifecycle:
                await lifecycle.activate()
        assert "cleanup also failed" in caught.value.__notes__[0]

    asyncio.run(exercise())
    assert read(tmp_path, "command.json")["output"]["stderr"] == rig.output.stderr
    assert read(tmp_path, "cleanup-command.json")["error"] is not None


def test_cleanup_failure_is_not_silently_successful(tmp_path):
    rig = Rig(tmp_path)
    rig.cleanup_error = WindCommandError("disable failed")

    async def exercise():
        with pytest.raises(WindCommandError, match="disable failed"):
            async with rig.managed() as lifecycle:
                await lifecycle.activate()
                assert (await lifecycle.prove_activation()).activated

    asyncio.run(exercise())
    assert read(tmp_path, "cleanup-command.json")["error"] is not None


def test_existing_evidence_is_not_reused_or_cleaned(tmp_path):
    rig = Rig(tmp_path)
    directory = tmp_path / "evidence/wind"
    directory.mkdir()
    sentinel = directory / "keep.txt"
    sentinel.write_text("existing")

    async def exercise():
        with pytest.raises(FileExistsError):
            async with rig.managed():
                pytest.fail("must not enter")

    asyncio.run(exercise())
    assert sentinel.read_text() == "existing"
    assert list(directory.iterdir()) == [sentinel]
    assert rig.commands == []


def test_controller_contract_and_out_of_order_call(tmp_path):
    rig = Rig(tmp_path)
    controller = GazeboWindController(stimulus(), tmp_path)
    assert isinstance(controller, FaultController)
    with pytest.raises(FaultLifecycleError):
        asyncio.run(controller.activate())
    assert rig.commands == []


def test_cancellation_during_cleanup_waits_for_disable(tmp_path):
    rig = Rig(tmp_path)

    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()

        async def runner(argv, *, timeout_s):
            if "enable_wind: false" in argv[-1]:
                started.set()
                await release.wait()
            return await rig.runner(argv, timeout_s=timeout_s)

        controller = GazeboWindController(
            stimulus(), tmp_path, runner=runner,
            observer=rig.observe, clock=rig.clock,
        )
        await controller.prepare()
        await controller.activate()
        task = asyncio.create_task(controller.cleanup())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await controller.cleanup()

    asyncio.run(exercise())
    assert len(rig.commands) == 2


@pytest.mark.parametrize("filename", ["command.json", "activation.json"])
def test_evidence_write_failure_aborts_and_disables(tmp_path, monkeypatch, filename):
    rig = Rig(tmp_path)
    publish = module.publish_text_exclusively

    def fail_selected(path, contents):
        if path.name == filename:
            raise OSError("disk full")
        publish(path, contents)

    monkeypatch.setattr(module, "publish_text_exclusively", fail_selected)

    async def exercise():
        with pytest.raises(OSError, match="disk full"):
            async with rig.managed() as lifecycle:
                await lifecycle.activate()
                await lifecycle.prove_activation()

    asyncio.run(exercise())
    assert len(rig.commands) == 2
    assert not (tmp_path / "evidence/wind/activation.json").exists()
    assert read(tmp_path, "cleanup-command.json")["error"] is None


@pytest.mark.parametrize("block_cleanup", [False, True])
def test_nonreturning_runner_is_bounded(tmp_path, block_cleanup):
    rig = Rig(tmp_path)
    calls = []
    cancelled = []

    async def runner(argv, *, timeout_s):
        is_cleanup = "enable_wind: false" in argv[-1]
        calls.append(is_cleanup)
        if is_cleanup == block_cleanup:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(is_cleanup)
        return await rig.runner(argv, timeout_s=timeout_s)

    async def exercise():
        with pytest.raises(TimeoutError):
            async with managed_wind_controller(
                stimulus(), tmp_path, runner=runner,
                observer=rig.observe, clock=rig.clock,
            ) as lifecycle:
                await lifecycle.activate()

    asyncio.run(exercise())
    assert calls == [False, True]
    assert cancelled == [block_cleanup]
    filename = "cleanup-command.json" if block_cleanup else "command.json"
    assert read(tmp_path, filename)["error"]["type"] == "TimeoutError"