# safe lifecycle management for external UAV-CI processes

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import signal

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


# start a managed process
async def start_managed_process(
    run_directory: RunDirectory,
    spec: ProcessSpec,
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