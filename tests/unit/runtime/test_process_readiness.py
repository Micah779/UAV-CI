# tests for process readiness detection

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID

import pytest

from uav_ci.runtime import (
    ProcessExitedBeforeReady,
    ProcessReadinessTimeout,
    ProcessSpec,
    create_run_directory,
    start_managed_process,
    stop_managed_process,
    wait_for_process_readiness,
)


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
    program: str,
) -> ProcessSpec:
    return ProcessSpec(
        process_id="readiness_process",
        command=(
            sys.executable,
            "-c",
            program,
        ),
        cwd=tmp_path.resolve(),
        shutdown_timeout_s=2,
    )


def test_stdout_marker_proves_readiness(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                "import time; "
                "time.sleep(0.05); "
                "print('SYSTEM READY', flush=True); "
                "time.sleep(30)"
            ),
        )
        managed = await start_managed_process(
            run_directory,
            spec,
        )

        try:
            readiness = (
                await wait_for_process_readiness(
                    managed,
                    marker="SYSTEM READY",
                    timeout_s=2,
                    poll_interval_s=0.01,
                )
            )

            assert readiness.stream == "stdout"
            assert readiness.marker == "SYSTEM READY"
            assert (
                readiness.matched_line
                == "SYSTEM READY"
            )
        finally:
            await stop_managed_process(managed)

    asyncio.run(exercise())


def test_stderr_marker_proves_readiness(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                "import sys, time; "
                "time.sleep(0.05); "
                "print('READY ON STDERR', "
                "file=sys.stderr, flush=True); "
                "time.sleep(30)"
            ),
        )
        managed = await start_managed_process(
            run_directory,
            spec,
        )

        try:
            readiness = (
                await wait_for_process_readiness(
                    managed,
                    marker="READY ON STDERR",
                    timeout_s=2,
                    poll_interval_s=0.01,
                )
            )

            assert readiness.stream == "stderr"
            assert "READY ON STDERR" in (
                readiness.matched_line
            )
        finally:
            await stop_managed_process(managed)

    asyncio.run(exercise())


def test_early_exit_is_reported(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            (
                "print('startup failed', flush=True); "
                "raise SystemExit(7)"
            ),
        )
        managed = await start_managed_process(
            run_directory,
            spec,
        )

        with pytest.raises(
            ProcessExitedBeforeReady,
            match="code 7",
        ) as exc_info:
            await wait_for_process_readiness(
                managed,
                marker="SYSTEM READY",
                timeout_s=2,
                poll_interval_s=0.01,
            )

        assert "startup failed" in str(
            exc_info.value
        )

    asyncio.run(exercise())


def test_readiness_timeout_preserves_cleanup_ownership(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            "import time; time.sleep(30)",
        )
        managed = await start_managed_process(
            run_directory,
            spec,
        )

        try:
            with pytest.raises(
                ProcessReadinessTimeout,
                match="did not produce marker",
            ):
                await wait_for_process_readiness(
                    managed,
                    marker="SYSTEM READY",
                    timeout_s=0.1,
                    poll_interval_s=0.01,
                )

            assert managed.process.returncode is None
        finally:
            await stop_managed_process(managed)

        assert managed.process.returncode is not None

    asyncio.run(exercise())


def test_invalid_readiness_limits_are_rejected(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        run_directory = create_test_run(tmp_path)
        spec = process_spec(
            tmp_path,
            "import time; time.sleep(30)",
        )
        managed = await start_managed_process(
            run_directory,
            spec,
        )

        invalid_arguments = (
            {
                "marker": "",
                "timeout_s": 1,
                "poll_interval_s": 0.01,
            },
            {
                "marker": "READY",
                "timeout_s": 0,
                "poll_interval_s": 0.01,
            },
            {
                "marker": "READY",
                "timeout_s": 1,
                "poll_interval_s": 0,
            },
        )

        try:
            for arguments in invalid_arguments:
                with pytest.raises(ValueError):
                    await wait_for_process_readiness(
                        managed,
                        **arguments,
                    )
        finally:
            await stop_managed_process(managed)

    asyncio.run(exercise())