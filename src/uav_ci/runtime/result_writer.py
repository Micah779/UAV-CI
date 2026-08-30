# validate and publish immutable UAV-CI run results

from pathlib import Path

from uav_ci.domain.manifest import RunManifest
from uav_ci.domain.result import RunResult
from uav_ci.runtime.files import (
    publish_text_exclusively,
)
from uav_ci.runtime.run_directory import RunDirectory


def write_run_result(
    run_directory: RunDirectory,
    manifest: RunManifest,
    result: RunResult,
) -> Path:
    # publish a result bound to its run manifest

    if manifest.run_id != run_directory.run_id:
        raise ValueError(
            "manifest run_id does not match run directory"
        )

    if manifest.scenario_id != run_directory.scenario_id:
        raise ValueError(
            "manifest scenario_id does not match "
            "run directory"
        )

    if manifest.started_at != run_directory.started_at:
        raise ValueError(
            "manifest started_at does not match "
            "run directory"
        )

    if result.run_id != manifest.run_id:
        raise ValueError(
            "result run_id does not match run manifest"
        )

    if result.scenario_id != manifest.scenario_id:
        raise ValueError(
            "result scenario_id does not match "
            "run manifest"
        )

    if result.scenario_hash != manifest.scenario_hash:
        raise ValueError(
            "result scenario_hash does not match "
            "run manifest"
        )

    if (
        result.requires_activation
        is not manifest.requires_activation
    ):
        raise ValueError(
            "result activation requirement does not "
            "match run manifest"
        )

    if result.started_at != manifest.started_at:
        raise ValueError(
            "result started_at does not match "
            "run manifest"
        )

    contents = result.model_dump_json(
        indent=2,
    ) + "\n"

    publish_text_exclusively(
        run_directory.result_path,
        contents,
    )

    return run_directory.result_path