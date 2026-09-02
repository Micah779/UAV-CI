# command-layer tests: no PX4 or Gazebo instance is contacted.

import asyncio
import signal
import sys

import pytest
from pydantic import ValidationError

from uav_ci.domain.scenario import WindStimulusSpec
from uav_ci.faults import wind_command as module
from uav_ci.faults.wind_command import (
    CommandOutput,
    GazeboWindCommandAdapter,
    WindCommand,
    WindCommandError,
    run_gazebo_command,
)


def stimulus(direction: float = 90.0) -> WindStimulusSpec:
    return WindStimulusSpec(
        type="wind",
        speed_m_s=5.0,
        direction_from_world_x_deg=direction,
        minimum_proven_speed_m_s=4.5,
        activation_timeout_s=5,
        activation_check_ids=(
            "wind_reached_vehicle",
        ),
    )


@pytest.mark.parametrize(
    ("direction", "expected_x", "expected_y"),
    [
        (0.0, 5.0, 0.0),
        (90.0, 0.0, 5.0),
        (180.0, -5.0, 0.0),
        (270.0, 0.0, -5.0),
    ],
)
def test_world_frame_direction(
    direction,
    expected_x,
    expected_y,
):
    command = WindCommand.from_stimulus(
        stimulus(direction)
    )

    assert command.x_m_s == pytest.approx(
        expected_x,
        abs=1e-12,
    )
    assert command.y_m_s == pytest.approx(
        expected_y,
        abs=1e-12,
    )
    assert command.z_m_s == 0
    assert command.enable_wind is True


def test_arguments_use_one_payload_and_fixed_world():
    command = WindCommand(
        x_m_s=0,
        y_m_s=5,
    )

    assert command.arguments() == (
        "gz",
        "topic",
        "-t",
        "/world/default/wind",
        "-m",
        "gz.msgs.Wind",
        "-p",
        "linear_velocity: {x: 0, y: 5, z: 0}, enable_wind: true",
    )


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_nonfinite_velocity_is_rejected(value):
    with pytest.raises(ValidationError):
        WindCommand(
            x_m_s=value,
            y_m_s=0,
        )


def test_command_is_strict_and_immutable():
    with pytest.raises(ValidationError):
        WindCommand(
            x_m_s="5",
            y_m_s=0,
        )

    with pytest.raises(ValidationError):
        WindCommand(
            x_m_s=5,
            y_m_s=0,
            enable_wind="true",
        )

    command = WindCommand(
        x_m_s=5,
        y_m_s=0,
    )

    with pytest.raises(ValidationError):
        command.x_m_s = 8


class FakeRunner:
    def __init__(
        self,
        output=CommandOutput(0, "", ""),
    ):
        self.output = output
        self.calls = []

    async def __call__(
        self,
        argv,
        *,
        timeout_s,
    ):
        self.calls.append((argv, timeout_s))
        return self.output


def test_send_returns_command_receipt_not_activation():
    runner = FakeRunner()
    adapter = GazeboWindCommandAdapter(
        timeout_s=2,
        runner=runner,
    )
    command = WindCommand.from_stimulus(
        stimulus()
    )

    receipt = asyncio.run(
        adapter.send(command)
    )

    assert runner.calls == [
        (command.arguments(), 2)
    ]
    assert receipt.argv == command.arguments()
    assert receipt.output.returncode == 0
    assert (
        receipt.finished_monotonic_ns
        >= receipt.started_monotonic_ns
    )
    assert not hasattr(receipt, "activated")


def test_disable_requests_zero_velocity_and_false():
    runner = FakeRunner()
    adapter = GazeboWindCommandAdapter(
        runner=runner
    )

    receipt = asyncio.run(adapter.disable())

    assert receipt.argv[-1] == (
        "linear_velocity: {x: 0, y: 0, z: 0}, "
        "enable_wind: false"
    )


@pytest.mark.parametrize(
    "output",
    [
        CommandOutput(
            1,
            "",
            "publish failed",
        ),
        CommandOutput(
            0,
            "",
            "Unable to create message",
        ),
    ],
)
def test_reported_command_errors_are_not_receipts(output):
    adapter = GazeboWindCommandAdapter(
        runner=FakeRunner(output)
    )

    with pytest.raises(
        WindCommandError,
        match="reported a failure",
    ):
        asyncio.run(
            adapter.send(
                WindCommand(
                    x_m_s=5,
                    y_m_s=0,
                )
            )
        )


@pytest.mark.parametrize(
    "timeout",
    [
        0,
        -1,
        float("inf"),
        float("nan"),
        True,
    ],
)
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(
        ValueError,
        match="finite and positive",
    ):
        GazeboWindCommandAdapter(
            timeout_s=timeout
        )


def test_runner_captures_output_without_shell_expansion():
    output = asyncio.run(
        run_gazebo_command(
            (
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print(sys.argv[1]); "
                    "print('diagnostic', file=sys.stderr)"
                ),
                "$(not-a-command)",
            ),
            timeout_s=5,
        )
    )

    assert output.returncode == 0
    assert output.stdout.strip() == "$(not-a-command)"
    assert output.stderr.strip() == "diagnostic"


def test_missing_executable_is_reported(monkeypatch):
    async def missing(*args, **kwargs):
        raise FileNotFoundError("gz missing")

    monkeypatch.setattr(
        module.asyncio,
        "create_subprocess_exec",
        missing,
    )

    with pytest.raises(
        WindCommandError,
        match="could not start",
    ):
        asyncio.run(
            run_gazebo_command(
                ("gz",),
                timeout_s=1,
            )
        )


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancellation_reap_publisher(
    monkeypatch,
    cancel,
):
    async def exercise():
        communicating = asyncio.Event()
        stopped = asyncio.Event()
        kills = []

        class FakeProcess:
            pid = 12345
            returncode = None

            async def communicate(self):
                communicating.set()
                await stopped.wait()

                self.returncode = -9
                return b"", b""

        process = FakeProcess()

        async def spawn(*args, **kwargs):
            assert kwargs["start_new_session"] is True
            assert (
                kwargs["env"]["GZ_IP"]
                == "127.0.0.1"
            )
            return process

        def killpg(pid, sig):
            kills.append((pid, sig))
            stopped.set()

        monkeypatch.setattr(
            module.asyncio,
            "create_subprocess_exec",
            spawn,
        )
        monkeypatch.setattr(
            module.os,
            "killpg",
            killpg,
        )

        task = asyncio.create_task(
            run_gazebo_command(
                ("gz", "topic"),
                timeout_s=10 if cancel else 0.01,
            )
        )
        await communicating.wait()

        if cancel:
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(
                WindCommandError,
                match="delivery is unknown",
            ):
                await task

        assert kills == [
            (process.pid, signal.SIGKILL)
        ]
        assert process.returncode == -9

    asyncio.run(exercise())