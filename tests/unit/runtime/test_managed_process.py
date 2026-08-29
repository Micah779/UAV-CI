# tests for safe managed-process lifecycle behavior

import asyncio
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

from uav_ci.runtime import (
    ProcessSpec,
    create_run_directory,
    start_managed_process,
    stop_managed_process,
    wait_managed_process,
)

from datetime import datetime, timezone
from uuid import UUID


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
STARTED_AT = datetime(
    2026,
    8,
    29,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_test_run(tmp_path: Path):
    return create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )


def process_spec(
    tmp_path: Path,
    command: tuple[str, ...],
    *,
    process_id: str = "test_process",
) -> ProcessSpec:
    return ProcessSpec(
        process_id=process_id,
        command=command,
        cwd=tmp_path.resolve(),
        shutdown_timeout_s=2,
    )


def test_invalid_process_specs_are_rejected(
    tmp_path: Path,
) -> None:
    invalid_specs = (
        {
            "process_id": "test_process",
            "command": (),
            "cwd": tmp_path.resolve(),
        },
        {
            "process_id": "test_process",
            "command": (sys.executable,),
            "cwd": Path("relative/path"),
        },
        {
            "process_id": "test_process",
            "command": (sys.executable,),
            "cwd": tmp_path.resolve(),
            "shutdown_timeout_s": 0,
        },
    )

    for data in invalid_specs:
        with pytest.raises(ValidationError):
            ProcessSpec.model_validate(data)


def test_process_output_is_captured(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print('standard output'); "
                    "print('standard error', "
                    "file=sys.stderr)"
                ),
            ),
        )

        managed = await start_managed_process(
            run_directory,
            spec,
        )
        returncode = await wait_managed_process(
            managed,
            timeout_s=5,
        )

        assert returncode == 0
        assert managed.stdout_path.read_text(
            encoding="utf-8"
        ).strip() == "standard output"
        assert managed.stderr_path.read_text(
            encoding="utf-8"
        ).strip() == "standard error"

    asyncio.run(exercise())


def test_nonzero_exit_code_is_retained(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ),
        )

        managed = await start_managed_process(
            run_directory,
            spec,
        )
        returncode = await wait_managed_process(
            managed,
            timeout_s=5,
        )

        assert returncode == 7

    asyncio.run(exercise())


def test_command_arguments_are_not_shell_expanded(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        literal_argument = "$(echo injected)"

        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print(sys.argv[1])"
                ),
                literal_argument,
            ),
        )

        managed = await start_managed_process(
            run_directory,
            spec,
        )
        returncode = await wait_managed_process(
            managed,
            timeout_s=5,
        )

        assert returncode == 0
        assert managed.stdout_path.read_text(
            encoding="utf-8"
        ).strip() == literal_argument

    asyncio.run(exercise())


def test_long_running_process_is_stopped(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
            ),
        )

        managed = await start_managed_process(
            run_directory,
            spec,
        )

        returncode = await stop_managed_process(
            managed
        )

        assert returncode != 0
        assert managed.process.returncode is not None

    asyncio.run(exercise())


def test_existing_process_logs_are_not_overwritten(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                "print('first run')",
            ),
        )

        first = await start_managed_process(
            run_directory,
            spec,
        )
        await wait_managed_process(
            first,
            timeout_s=5,
        )

        original_output = (
            first.stdout_path.read_text(
                encoding="utf-8"
            )
        )

        with pytest.raises(FileExistsError):
            await start_managed_process(
                run_directory,
                spec,
            )

        assert first.stdout_path.read_text(
            encoding="utf-8"
        ) == original_output

    asyncio.run(exercise())

def test_explicit_process_environment_is_used(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                sys.executable,
                "-c",
                (
                    "import os; "
                    "print("
                    "os.environ['UAV_CI_TEST_VALUE']"
                    ")"
                ),
            ),
        )

        managed = await start_managed_process(
            run_directory,
            spec,
            environment={
                "UAV_CI_TEST_VALUE": (
                    "px4-environment"
                ),
            },
        )

        returncode = await wait_managed_process(
            managed,
            timeout_s=5,
        )

        assert returncode == 0
        assert managed.stdout_path.read_text(
            encoding="utf-8"
        ).strip() == "px4-environment"

    asyncio.run(exercise())