'''
Purpose: test collection, evidence retention, deadlines, and cancellation without contacting a simulator.
The fake runner returns your saved snapshots as though Gazebo had just returned them.
'''

# observer tests use fake commands; no simulator is contacted.

import asyncio
from contextlib import aclosing
import json
from pathlib import Path

import pytest

from uav_ci.faults import wind_observer as module
from uav_ci.faults.wind_command import (
    CommandOutput,
    WindCommandError,
)


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "gazebo"
)

DIAGNOSTIC = (
    "I0902 11:55:14.180964 6775763 ev_poll_posix.cc:593] "
    "FD from fork parent still in poll list:fd(13, generation: 1)\n"
)


def snapshot(index=1):
    return (
        FIXTURES / f"gazebo-state-{index}.txt"
    ).read_text(encoding="utf-8")


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or [
            CommandOutput(0, snapshot(), "")
        ]
        self.calls = []

    async def __call__(self, argv, *, timeout_s):
        output = self.outputs[
            min(
                len(self.calls),
                len(self.outputs) - 1,
            )
        ]
        self.calls.append((argv, timeout_s))

        if isinstance(output, Exception):
            raise output

        return output


async def collect(path, runner, **options):
    settings = dict(
        max_samples=2,
        poll_interval_s=0.001,
    )
    settings.update(options)

    async with aclosing(
        module.observe_wind(
            path,
            runner=runner,
            **settings,
        )
    ) as stream:
        return [
            sample
            async for sample in stream
        ]


def record(path, index=1):
    return json.loads(
        (
            path / f"sample-{index:06d}.json"
        ).read_text()
    )


def test_two_samples_are_saved_before_delivery(tmp_path):
    async def exercise():
        path = tmp_path / "observations"
        runner = FakeRunner([
            CommandOutput(0, snapshot(1), ""),
            CommandOutput(0, snapshot(2), DIAGNOSTIC),
        ])

        samples = []

        async for sample in module.observe_wind(
            path,
            runner=runner,
            max_samples=2,
            poll_interval_s=0.001,
        ):
            assert sample.artifact_path.is_file()
            samples.append(sample)

        assert len(samples) == len(runner.calls) == 2

        assert (
            samples[1].observation.simulation_time_ns
            > samples[0].observation.simulation_time_ns
        )

        assert record(path, 1)["stdout"] == snapshot(1)
        assert record(path, 2)["stderr"] == DIAGNOSTIC
        assert record(path, 2)["error"] is None

        assert (
            record(path, 2)["observation"]["wind_velocity_world_m_s"]
            == [0.0, 0.0, 0.0]
        )

        assert (
            record(path, 2)["request_finished_monotonic_ns"]
            >= record(path, 2)["request_started_monotonic_ns"]
        )

        assert not hasattr(samples[0], "activated")

        assert runner.calls[0][0] == (
            "gz",
            "service",
            "-s",
            "/world/default/state",
            "--reqtype",
            "gz.msgs.Empty",
            "--reptype",
            "gz.msgs.SerializedStepMap",
            "--timeout",
            "2000",
            "--req",
            "",
        )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "stderr",
    [
        DIAGNOSTIC,
        DIAGNOSTIC.replace(":fd(", ": fd("),
    ],
)
def test_only_known_diagnostic_is_tolerated(tmp_path, stderr):
    runner = FakeRunner([
        CommandOutput(0, snapshot(), stderr)
    ])

    samples = asyncio.run(
        collect(
            tmp_path / "observations",
            runner,
            max_samples=1,
        )
    )

    assert len(samples) == 1


@pytest.mark.parametrize(
    "output",
    [
        CommandOutput(2, "", "command failed"),
        CommandOutput(0, "Service call failed", ""),
        CommandOutput(0, "", ""),
        CommandOutput(0, "stats {", ""),
    ],
)
def test_command_or_decode_failure_is_retained(tmp_path, output):
    path = tmp_path / "observations"

    with pytest.raises(
        module.WindObservationError,
        match="evidence:",
    ):
        asyncio.run(
            collect(path, FakeRunner([output]))
        )

    saved = record(path)

    assert saved["stdout"] == output.stdout
    assert saved["stderr"] == output.stderr
    assert saved["observation"] is None
    assert saved["error"] is not None


@pytest.mark.parametrize(
    "stderr",
    [
        "unexpected diagnostic",
        DIAGNOSTIC + "Service call timed out\n",
        DIAGNOSTIC.replace("I0902", "E0902"),
    ],
)
def test_valid_state_does_not_hide_unknown_stderr(tmp_path, stderr):
    path = tmp_path / "observations"

    with pytest.raises(module.WindObservationError):
        asyncio.run(
            collect(
                path,
                FakeRunner([
                    CommandOutput(0, snapshot(), stderr)
                ]),
            )
        )

    assert record(path)["stderr"] == stderr
    assert record(path)["observation"] is None


def test_nonzero_exit_is_not_excused_by_known_diagnostic(tmp_path):
    runner = FakeRunner([
        CommandOutput(1, snapshot(), DIAGNOSTIC)
    ])

    with pytest.raises(module.WindObservationError):
        asyncio.run(
            collect(
                tmp_path / "observations",
                runner,
            )
        )


def test_existing_directory_is_not_reused(tmp_path):
    path = tmp_path / "observations"
    path.mkdir()

    sentinel = path / "keep.txt"
    sentinel.write_text("existing evidence")

    runner = FakeRunner()

    with pytest.raises(FileExistsError):
        asyncio.run(collect(path, runner))

    assert runner.calls == []
    assert sentinel.read_text() == "existing evidence"


@pytest.mark.parametrize(
    "name,value",
    [
        ("timeout_s", 0),
        ("timeout_s", True),
        ("timeout_s", float("inf")),
        ("request_timeout_s", -1),
        ("request_timeout_s", float("nan")),
        ("poll_interval_s", 0),
        ("max_samples", True),
        ("max_samples", 0),
        ("max_samples", 1.5),
        ("max_samples", 1001),
    ],
)
def test_bad_configuration_has_no_side_effects(tmp_path, name, value):
    path = tmp_path / "observations"
    runner = FakeRunner()

    with pytest.raises(ValueError):
        asyncio.run(
            collect(
                path,
                runner,
                **{name: value},
            )
        )

    assert not path.exists()
    assert runner.calls == []


def test_timeout_cancels_runner_and_retains_attempt(tmp_path):
    async def exercise():
        cleaned = asyncio.Event()

        async def runner(argv, *, timeout_s):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        path = tmp_path / "observations"

        with pytest.raises(module.WindObservationTimeout):
            await collect(
                path,
                runner,
                request_timeout_s=0.02,
            )

        assert cleaned.is_set()
        assert record(path)["error"]["type"] == "TimeoutError"
        assert record(path)["stdout"] is None

    asyncio.run(exercise())


def test_external_cancellation_propagates(tmp_path):
    async def exercise():
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def runner(argv, *, timeout_s):
            started.set()

            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        path = tmp_path / "observations"
        task = asyncio.create_task(
            collect(path, runner)
        )

        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cleaned.is_set()
        assert record(path)["error"]["type"] == "CancelledError"

    asyncio.run(exercise())


def test_early_close_does_not_start_another_request(tmp_path):
    async def exercise():
        runner = FakeRunner()

        async with aclosing(
            module.observe_wind(
                tmp_path / "observations",
                runner=runner,
            )
        ) as stream:
            async for _ in stream:
                break

        assert len(runner.calls) == 1

    asyncio.run(exercise())


def test_failed_second_request_preserves_first_sample(tmp_path):
    path = tmp_path / "observations"

    runner = FakeRunner([
        CommandOutput(0, snapshot(), ""),
        WindCommandError("gz unavailable"),
    ])

    with pytest.raises(module.WindObservationError):
        asyncio.run(collect(path, runner))

    assert record(path, 1)["observation"] is not None
    assert (
        record(path, 2)["error"]["message"]
        == "gz unavailable"
    )


def test_no_sample_is_delivered_if_evidence_write_fails(
    tmp_path,
    monkeypatch,
):
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        module,
        "publish_text_exclusively",
        fail,
    )

    with pytest.raises(OSError, match="disk full"):
        asyncio.run(
            collect(
                tmp_path / "observations",
                FakeRunner(),
            )
        )


def test_observer_does_not_classify_paused_or_repeated_state(tmp_path):
    paused = snapshot().replace(
        "stats {",
        "stats { paused: true",
        1,
    )

    samples = asyncio.run(
        collect(
            tmp_path / "observations",
            FakeRunner([
                CommandOutput(0, paused, "")
            ]),
        )
    )

    assert all(
        sample.observation.paused
        for sample in samples
    )

    assert (
        samples[0].observation.simulation_time_ns
        == samples[1].observation.simulation_time_ns
    )


def test_late_response_is_saved_but_not_delivered(tmp_path):
    now = [0]

    async def runner(argv, *, timeout_s):
        assert timeout_s == 0.5
        now[0] = 600_000_000
        return CommandOutput(0, snapshot(), "")

    path = tmp_path / "observations"

    with pytest.raises(module.WindObservationTimeout):
        asyncio.run(
            collect(
                path,
                runner,
                timeout_s=0.5,
                clock=lambda: now[0],
            )
        )

    assert record(path)["stdout"] == snapshot()
    assert record(path)["observation"] is None


def test_total_budget_is_not_reset_between_requests(tmp_path):
    async def exercise():
        now = [0]
        runner = FakeRunner()

        stream = module.observe_wind(
            tmp_path / "observations",
            runner=runner,
            timeout_s=1,
            max_samples=2,
            clock=lambda: now[0],
        )

        async with aclosing(stream):
            await anext(stream)

            now[0] = 2_000_000_000

            with pytest.raises(module.WindObservationTimeout):
                await anext(stream)

        assert len(runner.calls) == 1

    asyncio.run(exercise())