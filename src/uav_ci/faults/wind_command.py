# bounded wind command publication for the pinned Gazebo world

import asyncio
from dataclasses import dataclass
import math
import os
import signal
from time import monotonic_ns
from typing import Protocol, Self
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, StrictBool

from uav_ci.domain.scenario import NumericValue, WindStimulusSpec

from uav_ci.faults.gazebo_diagnostics import has_unrecognized_stderr

WIND_TOPIC = "/world/default/wind"
WIND_MESSAGE_TYPE = "gz.msgs.Wind"


class WindCommandError(RuntimeError):
    # the publisher could not complete without a reported error.
    pass


class WindCommand(BaseModel):
    # requested world-frame velocity, not observed wind

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    x_m_s: NumericValue
    y_m_s: NumericValue
    z_m_s: NumericValue = 0
    enable_wind: StrictBool = True

    @classmethod
    def from_stimulus(cls, stimulus: WindStimulusSpec) -> Self:
        speed = float(stimulus.speed_m_s)

        if not math.isfinite(speed):
            raise ValueError("wind speed must be finite")

        angle = math.radians(
            stimulus.direction_from_world_x_deg
        )

        return cls(
            x_m_s=speed * math.cos(angle),
            y_m_s=speed * math.sin(angle),
            z_m_s=0,
            enable_wind=True,
        )

    @classmethod
    def disabled(cls) -> Self:
        return cls(
            x_m_s=0,
            y_m_s=0,
            z_m_s=0,
            enable_wind=False,
        )

    def arguments(self) -> tuple[str, ...]:
        enabled = "true" if self.enable_wind else "false"

        payload = (
            "linear_velocity: {"
            f"x: {self.x_m_s:.17g}, "
            f"y: {self.y_m_s:.17g}, "
            f"z: {self.z_m_s:.17g}"
            "}, "
            f"enable_wind: {enabled}"
        )

        return (
            "gz",
            "topic",
            "-t",
            WIND_TOPIC,
            "-m",
            WIND_MESSAGE_TYPE,
            "-p",
            payload,
        )


@dataclass(frozen=True, slots=True)
class CommandOutput:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class WindCommandReceipt:
    # this intentionally has no activated or passed field.

    argv: tuple[str, ...]
    started_monotonic_ns: int
    finished_monotonic_ns: int
    output: CommandOutput


class WindCommandRunner(Protocol):
    async def __call__(
        self,
        argv: tuple[str, ...],
        *,
        timeout_s: float,
    ) -> CommandOutput:
        ...


def _validate_timeout(timeout_s: float) -> None:
    if (
        isinstance(timeout_s, bool)
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise ValueError(
            "command timeout must be finite and positive"
        )


async def run_gazebo_command(
    argv: tuple[str, ...],
    *,
    timeout_s: float,
) -> CommandOutput:
    # run without a shell; reap the publisher on timeout/cancellation.

    _validate_timeout(timeout_s)

    environment = os.environ.copy()
    environment["GZ_IP"] = "127.0.0.1"

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=environment,
        )
    except OSError as exc:
        raise WindCommandError(
            f"could not start wind publisher: {exc}"
        ) from exc

    communication = asyncio.create_task(
        process.communicate()
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(communication),
            timeout=timeout_s,
        )
    except BaseException as exc:
        # The new session's process group contains only this publisher.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        await asyncio.shield(communication)

        if isinstance(exc, TimeoutError):
            raise WindCommandError(
                "wind publisher timed out; "
                "command delivery is unknown"
            ) from exc

        raise

    assert process.returncode is not None

    return CommandOutput(
        returncode=process.returncode,
        stdout=stdout.decode(
            "utf-8",
            errors="replace",
        ),
        stderr=stderr.decode(
            "utf-8",
            errors="replace",
        ),
    )


class GazeboWindCommandAdapter:
    # publish requests; leave activation proof to a separate observer.

    def __init__(
        self,
        *,
        timeout_s: float = 5.0,
        runner: WindCommandRunner = run_gazebo_command,
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        _validate_timeout(timeout_s)

        self._timeout_s = timeout_s
        self._runner = runner
        self._clock = clock

    async def send(
        self,
        request: WindCommand,
    ) -> WindCommandReceipt:
        argv = request.arguments()
        started = self._clock()

        output = await self._runner(
            argv,
            timeout_s=self._timeout_s,
        )

        finished = self._clock()

        # Gazebo CLI diagnostics may accompany a zero exit status.
        if output.returncode != 0 or has_unrecognized_stderr(output.stderr):
            details = (
                output.stderr.strip()
                or output.stdout.strip()
            )

            raise WindCommandError(
                "wind publisher reported a failure "
                f"(exit {output.returncode}): {details}"
            )

        return WindCommandReceipt(
            argv=argv,
            started_monotonic_ns=started,
            finished_monotonic_ns=finished,
            output=output,
        )

    async def disable(self) -> WindCommandReceipt:
        # Requests disabled + zero seed; does not prove restoration.
        return await self.send(
            WindCommand.disabled()
        )