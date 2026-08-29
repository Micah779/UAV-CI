# read-only verification of the installed PX4 environment

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from uav_ci.domain.environment import Sha256Digest
from uav_ci.domain.scenario import (
    EnvironmentProfileId,
    Identifier,
)
from uav_ci.environment import (
    LoadedEnvironmentProfile,
)


class PreflightCheckResult(BaseModel):
    # observed result of one environment check

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    check_id: Identifier
    passed: bool = Field(strict=True)
    expected: str = Field(min_length=1)
    observed: str = Field(min_length=1)
    command: tuple[str, ...] = ()


class EnvironmentPreflightResult(BaseModel):
    # complete read-only environment verification

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    profile_id: EnvironmentProfileId
    profile_hash: Sha256Digest
    px4_repository: Path
    checks: tuple[PreflightCheckResult, ...] = Field(
        min_length=1,
    )

    @field_validator("px4_repository")
    @classmethod
    def repository_path_must_be_absolute(
        cls,
        value: Path,
    ) -> Path:
        if not value.is_absolute():
            raise ValueError(
                "PX4 repository path must be absolute"
            )

        return value

    @model_validator(mode="after")
    def check_ids_must_be_unique(self) -> Self:
        check_ids = [
            check.check_id
            for check in self.checks
        ]

        if len(check_ids) != len(set(check_ids)):
            raise ValueError(
                "preflight check IDs must be unique"
            )

        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return all(
            check.passed
            for check in self.checks
        )

@dataclass(frozen=True, slots=True)
class CommandResult:
    # captured result of one read-only command

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[
    [tuple[str, ...], Path | None],
    CommandResult,
]


def run_command(
    command: tuple[str, ...],
    cwd: Path | None,
) -> CommandResult:
    # run one bounded command without a shell

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=10,
        )
    except OSError as exc:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            returncode=124,
            stdout="",
            stderr=str(exc),
        )

    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _observed_output(
    result: CommandResult,
) -> str:
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if stdout:
        return stdout

    if stderr:
        return stderr

    return f"exit code {result.returncode}"

def preflight_environment(
    loaded_environment: LoadedEnvironmentProfile,
    *,
    px4_repository: str | Path,
    runner: CommandRunner = run_command,
) -> EnvironmentPreflightResult:
    # compare the installed tools with a loaded profile

    profile = loaded_environment.profile
    repository = Path(px4_repository).resolve()
    checks: list[PreflightCheckResult] = []

    repository_exists = repository.is_dir()
    checks.append(
        PreflightCheckResult(
            check_id="px4_repository_exists",
            passed=repository_exists,
            expected="directory exists",
            observed=(
                "directory exists"
                if repository_exists
                else "directory missing"
            ),
        )
    )

    if repository_exists:
        revision_command = (
            "git",
            "rev-parse",
            "HEAD",
        )
        revision_result = runner(
            revision_command,
            repository,
        )
        observed_revision = _observed_output(
            revision_result
        )

        checks.append(
            PreflightCheckResult(
                check_id="px4_revision_matches",
                passed=(
                    revision_result.returncode == 0
                    and observed_revision
                    == profile.px4.revision
                ),
                expected=profile.px4.revision,
                observed=observed_revision,
                command=revision_command,
            )
        )

        status_command = (
            "git",
            "status",
            "--porcelain",
        )
        status_result = runner(
            status_command,
            repository,
        )
        status_output = status_result.stdout.strip()
        worktree_clean = (
            status_result.returncode == 0
            and status_output == ""
        )

        checks.append(
            PreflightCheckResult(
                check_id="px4_worktree_clean",
                passed=worktree_clean,
                expected="clean",
                observed=(
                    "clean"
                    if worktree_clean
                    else _observed_output(status_result)
                ),
                command=status_command,
            )
        )

        px4_python = (
            repository
            / ".venv"
            / "bin"
            / "python"
        )
        px4_python_exists = px4_python.is_file()

        checks.append(
            PreflightCheckResult(
                check_id="px4_python_exists",
                passed=px4_python_exists,
                expected="file exists",
                observed=(
                    "file exists"
                    if px4_python_exists
                    else "file missing"
                ),
            )
        )

        if px4_python_exists:
            import_command = (
                str(px4_python),
                "-c",
                (
                    "import kconfiglib; "
                    "import menuconfig"
                ),
            )
            import_result = runner(
                import_command,
                repository,
            )

            checks.append(
                PreflightCheckResult(
                    check_id=(
                        "px4_python_dependencies"
                    ),
                    passed=(
                        import_result.returncode
                        == 0
                    ),
                    expected=(
                        "kconfiglib and menuconfig "
                        "import successfully"
                    ),
                    observed=(
                        "imports succeeded"
                        if import_result.returncode
                        == 0
                        else _observed_output(
                            import_result
                        )
                    ),
                    command=import_command,
                )
            )

    gazebo_models_directory = (
        repository / "Tools" / "simulation" / "gz"
    )
    submodule_exists = (
        gazebo_models_directory.is_dir()
    )

    checks.append(
        PreflightCheckResult(
            check_id="gazebo_models_directory_exists",
            passed=submodule_exists,
            expected="directory exists",
            observed=(
                "directory exists"
                if submodule_exists
                else "directory missing"
            ),
        )
    )

    if submodule_exists:
        submodule_revision_command = (
            "git",
            "rev-parse",
            "HEAD",
        )
        submodule_revision_result = runner(
            submodule_revision_command,
            gazebo_models_directory,
        )
        observed_submodule_revision = (
            _observed_output(
                submodule_revision_result
            )
        )

        checks.append(
            PreflightCheckResult(
                check_id=(
                    "gazebo_models_revision_matches"
                ),
                passed=(
                    submodule_revision_result.returncode
                    == 0
                    and observed_submodule_revision
                    == profile.px4.gazebo_models_revision
                ),
                expected=(
                    profile.px4.gazebo_models_revision
                ),
                observed=observed_submodule_revision,
                command=submodule_revision_command,
            )
        )

        submodule_status_command = (
            "git",
            "status",
            "--porcelain",
        )
        submodule_status_result = runner(
            submodule_status_command,
            gazebo_models_directory,
        )
        submodule_status_output = (
            submodule_status_result.stdout.strip()
        )
        submodule_clean = (
            submodule_status_result.returncode == 0
            and submodule_status_output == ""
        )

        checks.append(
            PreflightCheckResult(
                check_id=(
                    "gazebo_models_worktree_clean"
                ),
                passed=submodule_clean,
                expected="clean",
                observed=(
                    "clean"
                    if submodule_clean
                    else _observed_output(
                        submodule_status_result
                    )
                ),
                command=submodule_status_command,
            )
        )

    gazebo_command = (
        "gz",
        "sim",
        "--version",
    )
    gazebo_result = runner(
        gazebo_command,
        None,
    )
    gazebo_output = (
        f"{gazebo_result.stdout}\n"
        f"{gazebo_result.stderr}"
    ).strip()
    expected_gazebo_version = (
        f"version {profile.gazebo.version}"
    )

    checks.append(
        PreflightCheckResult(
            check_id="gazebo_version_matches",
            passed=(
                gazebo_result.returncode == 0
                and expected_gazebo_version
                in gazebo_output
            ),
            expected=profile.gazebo.version,
            observed=(
                gazebo_output
                if gazebo_output
                else _observed_output(gazebo_result)
            ),
            command=gazebo_command,
        )
    )

    make_command = (
        "make",
        "--version",
    )
    make_result = runner(
        make_command,
        None,
    )

    checks.append(
        PreflightCheckResult(
            check_id="make_available",
            passed=make_result.returncode == 0,
            expected="available",
            observed=_observed_output(make_result),
            command=make_command,
        )
    )

    return EnvironmentPreflightResult(
        profile_id=profile.profile_id,
        profile_hash=loaded_environment.profile_hash,
        px4_repository=repository,
        checks=tuple(checks),
    )