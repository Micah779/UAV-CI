# isolated Gazebo model preparation for wind scenarios

import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Protocol


WIND_ENABLED_MARKER = (
    "<enable_wind>true</enable_wind>"
)


class WindWorkspaceError(RuntimeError):
    # isolated wind-model preparation failed
    pass


class RunDirectoryPaths(Protocol):
    # paths required from a UAV-CI run directory

    inputs_dir: Path
    workspace_dir: Path


@dataclass(frozen=True, slots=True)
class PreparedWindModel:
    # run-owned Gazebo model prepared for wind

    models_root: Path
    model_directory: Path
    model_sdf_path: Path
    model_config_path: Path
    patch_path: Path


def _run_git_apply(
    command: tuple[str, ...],
    *,
    cwd: Path,
    stage: str,
) -> None:
    # apply inside cwd without discovering a parent repo

    environment = os.environ.copy()
    environment["GIT_CEILING_DIRECTORIES"] = str(
        cwd.parent
    )

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=10,
            env=environment,
        )
    except OSError as exc:
        raise WindWorkspaceError(
            f"wind patch {stage} could not run: {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise WindWorkspaceError(
            f"wind patch {stage} timed out"
        ) from exc

    if completed.returncode == 0:
        return

    details = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or f"exit code {completed.returncode}"
    )

    raise WindWorkspaceError(
        f"wind patch {stage} failed: {details}"
    )


def prepare_wind_model_workspace(
    run_directory: RunDirectoryPaths,
    *,
    px4_repository: str | Path,
    patch_path: str | Path,
) -> PreparedWindModel:
    # create and patch a run-owned x500_base copy

    repository = Path(px4_repository).resolve()
    inputs_directory = (
        run_directory.inputs_dir.resolve()
    )
    workspace_directory = (
        run_directory.workspace_dir.resolve()
    )
    resolved_patch = Path(patch_path).resolve()

    if not repository.is_dir():
        raise WindWorkspaceError(
            f"PX4 repository does not exist: "
            f"{repository}"
        )

    if not inputs_directory.is_dir():
        raise WindWorkspaceError(
            "run inputs directory does not exist"
        )

    if not workspace_directory.is_dir():
        raise WindWorkspaceError(
            "run workspace directory does not exist"
        )

    if (
        inputs_directory.parent
        != workspace_directory.parent
    ):
        raise WindWorkspaceError(
            "inputs and workspace must belong "
            "to the same run"
        )

    if not resolved_patch.is_file():
        raise WindWorkspaceError(
            f"wind patch does not exist: "
            f"{resolved_patch}"
        )

    if not resolved_patch.is_relative_to(
        inputs_directory
    ):
        raise WindWorkspaceError(
            "wind preparation requires a "
            "snapshotted run-input patch"
        )

    source_model_directory = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
        / "models"
        / "x500_base"
    )
    source_sdf_path = (
        source_model_directory / "model.sdf"
    )
    source_config_path = (
        source_model_directory / "model.config"
    )

    if not source_model_directory.is_dir():
        raise WindWorkspaceError(
            "PX4 x500_base model directory "
            "does not exist"
        )

    if not source_sdf_path.is_file():
        raise WindWorkspaceError(
            "PX4 x500_base model.sdf does not exist"
        )

    if not source_config_path.is_file():
        raise WindWorkspaceError(
            "PX4 x500_base model.config "
            "does not exist"
        )

    models_root = workspace_directory / "models"
    model_directory = (
        models_root / "x500_base"
    )

    if model_directory.exists():
        raise WindWorkspaceError(
            "run-owned x500_base model "
            "already exists"
        )

    source_sdf_before = source_sdf_path.read_bytes()

    with TemporaryDirectory(
        prefix=".wind-staging-",
        dir=workspace_directory,
    ) as temporary_directory:
        staging_root = Path(temporary_directory)
        staged_model_directory = (
            staging_root
            / "models"
            / "x500_base"
        )

        shutil.copytree(
            source_model_directory,
            staged_model_directory,
        )

        check_command = (
            "git",
            "apply",
            "--check",
            str(resolved_patch),
        )
        apply_command = (
            "git",
            "apply",
            str(resolved_patch),
        )

        _run_git_apply(
            check_command,
            cwd=staging_root,
            stage="check",
        )
        _run_git_apply(
            apply_command,
            cwd=staging_root,
            stage="application",
        )

        staged_sdf_path = (
            staged_model_directory / "model.sdf"
        )
        staged_contents = (
            staged_sdf_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            staged_contents.count(
                WIND_ENABLED_MARKER
            )
            != 1
        ):
            raise WindWorkspaceError(
                "patched model did not contain "
                "exactly one wind-enable marker"
            )

        models_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        staged_model_directory.rename(
            model_directory
        )

    if source_sdf_path.read_bytes() != source_sdf_before:
        raise WindWorkspaceError(
            "shared PX4 model changed during "
            "wind preparation"
        )

    return PreparedWindModel(
        models_root=models_root,
        model_directory=model_directory,
        model_sdf_path=(
            model_directory / "model.sdf"
        ),
        model_config_path=(
            model_directory / "model.config"
        ),
        patch_path=resolved_patch,
    )