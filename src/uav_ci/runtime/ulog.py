# capture the exact PX4 ULog announced by SITL

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from uav_ci.runtime.files import (
    publish_file_exclusively,
)
from uav_ci.runtime.run_directory import RunDirectory


PX4_ULOG_PATTERN = re.compile(
    r"Opened full log file:\s+"
    r"(?P<path>"
    r"\./log/"
    r"\d{4}-\d{2}-\d{2}/"
    r"\d{2}_\d{2}_\d{2}\.ulg"
    r")"
)


class ULogCaptureError(RuntimeError):
    # PX4 ULog could not be identified or captured
    pass


@dataclass(frozen=True, slots=True)
class CapturedULog:
    # identity of one captured PX4 ULog artifact

    path: Path
    source_relative_path: Path
    sha256: str
    size_bytes: int


def extract_ulog_relative_path(
    px4_stdout: str,
) -> Path:
    # extract exactly one PX4-announced ULog path

    matches = tuple(
        dict.fromkeys(
            match.group("path")
            for match in (
                PX4_ULOG_PATTERN.finditer(
                    px4_stdout
                )
            )
        )
    )

    if len(matches) != 1:
        raise ULogCaptureError(
            "expected exactly one PX4 ULog path "
            f"in stdout, found {len(matches)}"
        )

    relative_path = Path(matches[0])

    if relative_path.is_absolute():
        raise ULogCaptureError(
            "PX4 ULog path must be relative"
        )

    if ".." in relative_path.parts:
        raise ULogCaptureError(
            "PX4 ULog path cannot leave rootfs"
        )

    if (
        not relative_path.parts
        or relative_path.parts[0] != "log"
        or relative_path.suffix != ".ulg"
    ):
        raise ULogCaptureError(
            "PX4 ULog path is outside log/"
        )

    return relative_path


def _sha256_file(path: Path) -> str:
    digest = sha256()

    with path.open("rb") as input_file:
        while True:
            chunk = input_file.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def capture_px4_ulog(
    run_directory: RunDirectory,
    *,
    px4_repository: str | Path,
    process_stdout_path: str | Path,
) -> CapturedULog:
    # capture the ULog after PX4 has shut down

    stdout_path = Path(
        process_stdout_path
    ).resolve()

    if not stdout_path.is_file():
        raise ULogCaptureError(
            "PX4 stdout log does not exist: "
            f"{stdout_path}"
        )

    relative_path = extract_ulog_relative_path(
        stdout_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    repository = Path(
        px4_repository
    ).resolve()
    rootfs = (
        repository
        / "build"
        / "px4_sitl_default"
        / "rootfs"
    ).resolve()

    source_path = (
        rootfs / relative_path
    ).resolve()

    if not source_path.is_relative_to(rootfs):
        raise ULogCaptureError(
            "resolved ULog path leaves PX4 rootfs"
        )

    if not source_path.is_file():
        raise ULogCaptureError(
            "PX4 announced a ULog that does not "
            f"exist: {source_path}"
        )

    if source_path.stat().st_size == 0:
        raise ULogCaptureError(
            "PX4 ULog is empty"
        )

    publish_file_exclusively(
        source_path,
        run_directory.ulog_path,
    )

    return CapturedULog(
        path=run_directory.ulog_path,
        source_relative_path=relative_path,
        sha256=_sha256_file(
            run_directory.ulog_path
        ),
        size_bytes=(
            run_directory
            .ulog_path
            .stat()
            .st_size
        ),
    )