# tests for exact PX4 ULog capture

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.runtime import (
    ULogCaptureError,
    capture_px4_ulog,
    create_run_directory,
)


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
STARTED_AT = datetime(
    2026,
    8,
    30,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)
ULOG_RELATIVE_PATH = Path(
    "log/2026-08-30/12_00_05.ulg"
)


def make_run_directory(
    tmp_path: Path,
):
    return create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="baseline_mission",
        started_at=STARTED_AT,
    )


def make_px4_repository(
    tmp_path: Path,
    *,
    contents: bytes = b"test-ulog-contents",
) -> tuple[Path, Path]:
    repository = tmp_path / "PX4-Autopilot"
    source_path = (
        repository
        / "build"
        / "px4_sitl_default"
        / "rootfs"
        / ULOG_RELATIVE_PATH
    )
    source_path.parent.mkdir(
        parents=True
    )
    source_path.write_bytes(contents)

    return repository, source_path


def write_px4_stdout(
    tmp_path: Path,
    *relative_paths: Path,
) -> Path:
    stdout_path = tmp_path / "px4.stdout.log"

    lines = [
        (
            "INFO  [logger] Opened full log file: "
            f"./{path.as_posix()}"
        )
        for path in relative_paths
    ]

    stdout_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return stdout_path


def test_announced_ulog_is_captured_and_hashed(
    tmp_path: Path,
) -> None:
    contents = b"known-px4-ulog"
    repository, _ = make_px4_repository(
        tmp_path,
        contents=contents,
    )
    stdout_path = write_px4_stdout(
        tmp_path,
        ULOG_RELATIVE_PATH,
    )
    run_directory = make_run_directory(
        tmp_path
    )

    captured = capture_px4_ulog(
        run_directory,
        px4_repository=repository,
        process_stdout_path=stdout_path,
    )

    assert captured.path == (
        run_directory.ulog_path
    )
    assert captured.path.read_bytes() == contents
    assert captured.source_relative_path == (
        ULOG_RELATIVE_PATH
    )
    assert captured.size_bytes == len(contents)
    assert captured.sha256 == (
        sha256(contents).hexdigest()
    )


def test_missing_ulog_marker_is_rejected(
    tmp_path: Path,
) -> None:
    repository, _ = make_px4_repository(
        tmp_path
    )
    stdout_path = tmp_path / "px4.stdout.log"
    stdout_path.write_text(
        "PX4 started without a logger marker\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ULogCaptureError,
        match="exactly one",
    ):
        capture_px4_ulog(
            make_run_directory(tmp_path),
            px4_repository=repository,
            process_stdout_path=stdout_path,
        )


def test_multiple_ulog_paths_are_rejected(
    tmp_path: Path,
) -> None:
    repository, _ = make_px4_repository(
        tmp_path
    )
    stdout_path = write_px4_stdout(
        tmp_path,
        ULOG_RELATIVE_PATH,
        Path(
            "log/2026-08-30/12_05_00.ulg"
        ),
    )

    with pytest.raises(
        ULogCaptureError,
        match="found 2",
    ):
        capture_px4_ulog(
            make_run_directory(tmp_path),
            px4_repository=repository,
            process_stdout_path=stdout_path,
        )


def test_announced_missing_ulog_is_rejected(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "PX4-Autopilot"
    repository.mkdir()
    stdout_path = write_px4_stdout(
        tmp_path,
        ULOG_RELATIVE_PATH,
    )

    with pytest.raises(
        ULogCaptureError,
        match="does not exist",
    ):
        capture_px4_ulog(
            make_run_directory(tmp_path),
            px4_repository=repository,
            process_stdout_path=stdout_path,
        )


def test_existing_ulog_is_not_overwritten(
    tmp_path: Path,
) -> None:
    repository, _ = make_px4_repository(
        tmp_path
    )
    stdout_path = write_px4_stdout(
        tmp_path,
        ULOG_RELATIVE_PATH,
    )
    run_directory = make_run_directory(
        tmp_path
    )

    capture_px4_ulog(
        run_directory,
        px4_repository=repository,
        process_stdout_path=stdout_path,
    )
    original_contents = (
        run_directory.ulog_path.read_bytes()
    )

    with pytest.raises(FileExistsError):
        capture_px4_ulog(
            run_directory,
            px4_repository=repository,
            process_stdout_path=stdout_path,
        )

    assert (
        run_directory.ulog_path.read_bytes()
        == original_contents
    )