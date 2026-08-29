# build and persist immutable UAV-CI run manifests

from datetime import datetime
from importlib.metadata import version
import os
from pathlib import Path
import platform
from tempfile import mkstemp
from uuid import UUID

from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.runtime.run_directory import RunDirectory
from uav_ci.scenario import LoadedScenario
from uav_ci.environment import LoadedEnvironmentProfile

def detect_harness_provenance() -> HarnessProvenance:
    # describe the installed harness and Python runtime

    return HarnessProvenance(
        uav_ci_version=version("uav-ci"),
        python_version=platform.python_version(),
        platform=platform.platform(),
    )


def build_run_manifest(
    loaded_scenario: LoadedScenario,
    loaded_environment: LoadedEnvironmentProfile,
    *,
    run_id: UUID,
    started_at: datetime,
    repetition_index: int,
    harness: HarnessProvenance | None = None,
) -> RunManifest:
    # build the manifest for one scenario repetition

    scenario = loaded_scenario.scenario
    environment = loaded_environment.profile

    if (
        scenario.environment.profile
        != environment.profile_id
    ):
        raise ValueError(
            "scenario environment profile does not "
            "match loaded environment"
        )

    if harness is None:
        harness = detect_harness_provenance()

    return RunManifest(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        scenario_hash=loaded_scenario.scenario_hash,
        environment_profile=environment.profile_id,
        environment_hash=loaded_environment.profile_hash,
        requires_activation=scenario.requires_activation,
        repetition_index=repetition_index,
        repetition_count=scenario.execution.repetitions,
        seed=scenario.execution.seed,
        started_at=started_at,
        harness=harness,
    )


def _write_text_exclusively(
    target: Path,
    contents: str,
) -> None:
    # atomically publish text without overwriting a file

    file_descriptor, temporary_name = mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as temporary_file:
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # A hard link publishes the complete file and fails
        # atomically if the target already exists.
        os.link(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_run_manifest(
    run_directory: RunDirectory,
    manifest: RunManifest,
) -> Path:
    # write a manifest into its matching run directory

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

    contents = manifest.model_dump_json(indent=2) + "\n"

    _write_text_exclusively(
        run_directory.manifest_path,
        contents,
    )

    return run_directory.manifest_path