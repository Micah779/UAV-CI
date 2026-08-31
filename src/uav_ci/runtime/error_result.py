# build and publish terminal harness-error results

from datetime import datetime

from uav_ci.domain.manifest import RunManifest
from uav_ci.domain.result import RunResult
from uav_ci.runtime.result_writer import (
    write_run_result,
)
from uav_ci.runtime.run_directory import (
    RunDirectory,
)


def describe_harness_error(
    error: Exception,
) -> str:
    # preserve the exception type, message, and notes

    error_type = type(error).__name__
    detail = str(error).strip()

    description = (
        f"{error_type}: {detail}"
        if detail
        else error_type
    )

    notes = tuple(
        str(note).strip()
        for note in getattr(
            error,
            "__notes__",
            (),
        )
        if str(note).strip()
    )

    if notes:
        description += "\n" + "\n".join(
            f"note: {note}"
            for note in notes
        )

    return description


def build_harness_error_result(
    manifest: RunManifest,
    *,
    error: Exception,
    finished_at: datetime,
) -> RunResult:
    # represent incomplete harness execution as ERROR

    return RunResult(
        run_id=manifest.run_id,
        scenario_id=manifest.scenario_id,
        scenario_hash=manifest.scenario_hash,
        requires_activation=(
            manifest.requires_activation
        ),
        started_at=manifest.started_at,
        finished_at=finished_at,
        assertions=(),
        harness_error=describe_harness_error(
            error
        ),
    )


def write_harness_error_result(
    run_directory: RunDirectory,
    manifest: RunManifest,
    *,
    error: Exception,
    finished_at: datetime,
) -> RunResult:
    # build and exclusively publish an ERROR result

    result = build_harness_error_result(
        manifest,
        error=error,
        finished_at=finished_at,
    )

    write_run_result(
        run_directory,
        manifest,
        result,
    )

    return result