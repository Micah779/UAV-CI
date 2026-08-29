# safe lifecycle management for external UAV-CI processes

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import signal
from time import monotonic
from typing import Literal
from collections.abc import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)

from uav_ci.domain.scenario import Identifier
from uav_ci.runtime.run_directory import RunDirectory


class ProcessSpec(BaseModel):
    # validated configuration for one managed process

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    process_id: Identifier
    command: tuple[StrictStr, ...] = Field(
        min_length=1,
    )
    cwd: Path
    shutdown_timeout_s: int = Field(
        default=10,
        gt=0,
        strict=True,
    )

    @field_validator("cwd")
    @classmethod
    def cwd_must_be_absolute(
        cls,
        value: Path,
    ) -> Path:
        if not value.is_absolute():
            raise ValueError(
                "process cwd must be absolute"
            )

        return value


# represent a running process
@dataclass(frozen=True, slots=True)
class ManagedProcess:
    # a running child process and its retained logs

    spec: ProcessSpec
    process: asyncio.subprocess.Process
    stdout_path: Path
    stderr_path: Path

@dataclass(frozen=True, slots=True)
class ReadinessMatch:
    # the log observation that proved readiness

    process_id: str
    stream: Literal["stdout", "stderr"]
    marker: str
    matched_line: str
    elapsed_s: float


class ProcessExitedBeforeReady(RuntimeError):
    # raised when a process exits before readiness
    pass


class ProcessReadinessTimeout(TimeoutError):
    # raised when readiness is not proven in time
    pass

# start a managed process
async def start_managed_process(
    run_directory: RunDirectory,
    spec: ProcessSpec,
    *,
    environment: Mapping[str, str] | None = None,
) -> ManagedProcess:
    # start one process in an isolated process group

    if not spec.cwd.is_dir():
        raise ValueError(
            f"process cwd does not exist: {spec.cwd}"
        )

    stdout_path = (
        run_directory.logs_dir
        / f"{spec.process_id}.stdout.log"
    )
    stderr_path = (
        run_directory.logs_dir
        / f"{spec.process_id}.stderr.log"
    )

    stdout_file = stdout_path.open("xb")
    try:
        stderr_file = stderr_path.open("xb")
    except BaseException:
        stdout_file.close()
        raise

    try:
        process = await asyncio.create_subprocess_exec(
            *spec.command,
            cwd=spec.cwd,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
            env=(
                dict(environment)
                if environment is not None
                else None
            ),
        )
    finally:
        stdout_file.close()
        stderr_file.close()

    return ManagedProcess(
        spec=spec,
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


# wait for normal completion
async def wait_managed_process(
    managed: ManagedProcess,
    *,
    timeout_s: int | None = None,
) -> int:
    # wait for completion with an optional timeout

    if timeout_s is None:
        return await managed.process.wait()

    try:
        return await asyncio.wait_for(
            managed.process.wait(),
            timeout=timeout_s,
        )
    except TimeoutError as exc:
        raise TimeoutError(
            f"process {managed.spec.process_id} "
            f"did not exit within {timeout_s} seconds"
        ) from exc


async def wait_for_process_readiness(
    managed: ManagedProcess,
    *,
    marker: str,
    timeout_s: float,
    poll_interval_s: float = 0.05,
) -> ReadinessMatch:
    # wait until stdout or stderr proves readiness

    if not marker:
        raise ValueError(
            "readiness marker cannot be empty"
        )

    if timeout_s <= 0:
        raise ValueError(
            "readiness timeout must be positive"
        )

    if poll_interval_s <= 0:
        raise ValueError(
            "poll interval must be positive"
        )

    started = monotonic()
    deadline = started + timeout_s

    while True:
        stream_logs = (
            (
                "stdout",
                _read_process_log(
                    managed.stdout_path
                ),
            ),
            (
                "stderr",
                _read_process_log(
                    managed.stderr_path
                ),
            ),
        )

        for stream, contents in stream_logs:
            if marker in contents:
                matched_line = next(
                    (
                        line
                        for line in contents.splitlines()
                        if marker in line
                    ),
                    marker,
                )

                return ReadinessMatch(
                    process_id=(
                        managed.spec.process_id
                    ),
                    stream=stream,
                    marker=marker,
                    matched_line=matched_line,
                    elapsed_s=monotonic() - started,
                )

        if managed.process.returncode is not None:
            combined_output = "\n".join(
                contents
                for _, contents in stream_logs
                if contents
            )
            output_tail = combined_output[-1000:]

            raise ProcessExitedBeforeReady(
                f"process {managed.spec.process_id} "
                "exited before readiness with code "
                f"{managed.process.returncode}; "
                f"output tail: {output_tail!r}"
            )

        remaining_s = deadline - monotonic()

        if remaining_s <= 0:
            raise ProcessReadinessTimeout(
                f"process {managed.spec.process_id} "
                f"did not produce marker {marker!r} "
                f"within {timeout_s} seconds"
            )

        await asyncio.sleep(
            min(
                poll_interval_s,
                remaining_s,
            )
        )

# add bounded process group shutdown
async def stop_managed_process(
    managed: ManagedProcess,
) -> int:

    # stop a process group, escalating if necessary

    process = managed.process

    if process.returncode is not None:
        return process.returncode

    try:
        os.killpg(
            process.pid,
            signal.SIGTERM,
        )
    except ProcessLookupError:
        return await process.wait()

    try:
        return await asyncio.wait_for(
            process.wait(),
            timeout=managed.spec.shutdown_timeout_s,
        )
    except TimeoutError:
        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

        return await process.wait()


def _read_process_log(path: Path) -> str:
    # read a growing process log safely

    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return ""