# prepare a complete UAV-CI run without launching PX4

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import hmac
from pathlib import Path
from time import monotonic_ns
from uuid import UUID, uuid4

from uav_ci.clocks import utc_now
from uav_ci.domain.environment import EnvironmentProfile
from uav_ci.domain.manifest import (
    HarnessProvenance,
    RunManifest,
)
from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.environment import (
    LoadedEnvironmentProfile,
    load_environment_profile,
)
from uav_ci.runtime.files import (
    publish_bytes_exclusively,
    publish_text_exclusively,
)
from uav_ci.runtime.logging import (
    LogAttribute,
    StructuredEvent,
    append_event,
)
from uav_ci.runtime.manifest import (
    build_run_manifest,
    write_run_manifest,
)
from uav_ci.runtime.preflight import (
    CommandRunner,
    EnvironmentPreflightResult,
    preflight_environment,
    run_command,
)
from uav_ci.runtime.run_directory import (
    RunDirectory,
    create_run_directory,
)
from uav_ci.scenario import (
    LoadedScenario,
    load_scenario,
)


@dataclass(frozen=True, slots=True)
class InputSnapshots:
    # immutable validated inputs retained with a run

    scenario_path: Path
    environment_path: Path
    patch_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class PreparedRun:
    # a fully prepared run that has not launched PX4

    run_directory: RunDirectory
    manifest: RunManifest
    snapshots: InputSnapshots
    preflight: EnvironmentPreflightResult

    @property
    def ready(self) -> bool:
        return self.preflight.passed

# sanpshot validated inputs
def snapshot_run_inputs(
    run_directory: RunDirectory,
    loaded_scenario: LoadedScenario,
    loaded_environment: LoadedEnvironmentProfile,
) -> InputSnapshots:
    # persist validated scenario and environment inputs

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

    scenario_contents = (
        scenario.model_dump_json(indent=2) + "\n"
    )
    environment_contents = (
        environment.model_dump_json(indent=2) + "\n"
    )

    publish_text_exclusively(
        run_directory.scenario_snapshot_path,
        scenario_contents,
    )
    publish_text_exclusively(
        run_directory.environment_snapshot_path,
        environment_contents,
    )

    snapshot_patch_paths: list[Path] = []

    for patch, source_path in zip(
        environment.patches,
        loaded_environment.patch_paths,
        strict=True,
    ):
        patch_contents = source_path.read_bytes()
        actual_digest = sha256(
            patch_contents
        ).hexdigest()

        if not hmac.compare_digest(
            actual_digest,
            patch.sha256,
        ):
            raise ValueError(
                "environment patch changed after "
                f"profile loading: {patch.file}"
            )

        destination = (
            run_directory.input_patches_dir
            / f"{patch.patch_id}.patch"
        )

        publish_bytes_exclusively(
            destination,
            patch_contents,
        )
        snapshot_patch_paths.append(destination)

    return InputSnapshots(
        scenario_path=(
            run_directory.scenario_snapshot_path
        ),
        environment_path=(
            run_directory.environment_snapshot_path
        ),
        patch_paths=tuple(snapshot_patch_paths),
    )

# compose prepare_run()
def prepare_run(
    scenario_path: str | Path,
    environment_path: str | Path,
    *,
    px4_repository: str | Path,
    runs_root: str | Path = "artifacts/runs",
    repetition_index: int = 1,
    run_id: UUID | None = None,
    started_at: datetime | None = None,
    harness: HarnessProvenance | None = None,
    preflight_runner: CommandRunner = run_command,
    clock: Callable[[], datetime] = utc_now,
    monotonic_clock: Callable[
        [],
        int,
    ] = monotonic_ns,
) -> PreparedRun:
    # prepare and verify one run without launching PX4

    loaded_scenario = load_scenario(scenario_path)
    loaded_environment = load_environment_profile(
        environment_path
    )

    scenario = loaded_scenario.scenario

    if (
        scenario.environment.profile
        != loaded_environment.profile.profile_id
    ):
        raise ValueError(
            "scenario environment profile does not "
            "match loaded environment"
        )

    resolved_run_id = (
        run_id if run_id is not None else uuid4()
    )
    resolved_started_at = (
        started_at
        if started_at is not None
        else clock()
    )

    run_directory = create_run_directory(
        runs_root,
        run_id=resolved_run_id,
        scenario_id=scenario.scenario_id,
        started_at=resolved_started_at,
    )

    manifest = build_run_manifest(
        loaded_scenario,
        loaded_environment,
        run_id=resolved_run_id,
        started_at=resolved_started_at,
        repetition_index=repetition_index,
        harness=harness,
    )
    write_run_manifest(
        run_directory,
        manifest,
    )

    snapshots = snapshot_run_inputs(
        run_directory,
        loaded_scenario,
        loaded_environment,
    )

    append_event(
        run_directory,
        StructuredEvent(
            timestamp=clock(),
            monotonic_ns=monotonic_clock(),
            run_id=resolved_run_id,
            scenario_id=scenario.scenario_id,
            level="info",
            component="runtime",
            event="run_prepared",
            message=(
                "Run identity and input snapshots "
                "were created."
            ),
            attributes=(
                LogAttribute(
                    key="repetition_index",
                    value=repetition_index,
                ),
                LogAttribute(
                    key="environment_profile",
                    value=(
                        loaded_environment
                        .profile.profile_id
                    ),
                ),
            ),
        ),
    )

    preflight = preflight_environment(
        loaded_environment,
        px4_repository=px4_repository,
        runner=preflight_runner,
    )

    publish_text_exclusively(
        run_directory.preflight_path,
        preflight.model_dump_json(
            indent=2,
            exclude_computed_fields=True,
        )
        + "\n",
    )

    failed_count = sum(
        not check.passed
        for check in preflight.checks
    )

    append_event(
        run_directory,
        StructuredEvent(
            timestamp=clock(),
            monotonic_ns=monotonic_clock(),
            run_id=resolved_run_id,
            scenario_id=scenario.scenario_id,
            level=(
                "info"
                if preflight.passed
                else "warning"
            ),
            component="runtime",
            event="preflight_completed",
            message=(
                "Environment preflight passed."
                if preflight.passed
                else "Environment preflight failed."
            ),
            attributes=(
                LogAttribute(
                    key="check_count",
                    value=len(preflight.checks),
                ),
                LogAttribute(
                    key="failed_count",
                    value=failed_count,
                ),
            ),
        ),
    )

    return PreparedRun(
        run_directory=run_directory,
        manifest=manifest,
        snapshots=snapshots,
        preflight=preflight,
    )