# tests for read-only environment preflight

from pathlib import Path

from uav_ci.environment import (
    load_environment_profile,
)
from uav_ci.runtime import (
    CommandResult,
    preflight_environment,
)


PROJECT_ROOT = Path(__file__).parents[3]
PROFILE_PATH = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)

PX4_REVISION = (
    "e4a0bc726e20a6796c08786e3199771c5c914499"
)
GAZEBO_MODELS_REVISION = (
    "bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9"
)


class FakeRunner:
    # return predefined command observations

    def __init__(
        self,
        responses: dict[
            tuple[tuple[str, ...], Path | None],
            CommandResult,
        ],
    ) -> None:
        self.responses = responses

    def __call__(
        self,
        command: tuple[str, ...],
        cwd: Path | None,
    ) -> CommandResult:
        key = (
            command,
            cwd.resolve() if cwd is not None else None,
        )

        return self.responses.get(
            key,
            CommandResult(
                command=command,
                returncode=127,
                stdout="",
                stderr="unexpected command",
            ),
        )


def command_result(
    command: tuple[str, ...],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> CommandResult:
    return CommandResult(
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def compatible_environment(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[
        tuple[tuple[str, ...], Path | None],
        CommandResult,
    ],
]:
    repository = (
        tmp_path / "PX4-Autopilot"
    ).resolve()
    submodule = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
    )
    submodule.mkdir(parents=True)

    git_revision = (
        "git",
        "rev-parse",
        "HEAD",
    )
    git_status = (
        "git",
        "status",
        "--porcelain",
    )
    gazebo_version = (
        "gz",
        "sim",
        "--version",
    )
    make_version = (
        "make",
        "--version",
    )

    px4_python = (
        repository
        / ".venv"
        / "bin"
        / "python"
    )
    px4_python.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    px4_python.touch()

    px4_python_imports = (
        str(px4_python),
        "-c",
        (
            "import kconfiglib; "
            "import menuconfig"
        ),
    )

    responses = {
        (git_revision, repository): command_result(
            git_revision,
            stdout=f"{PX4_REVISION}\n",
        ),
        (git_status, repository): command_result(
            git_status,
            stdout="",
        ),
        (
            git_revision,
            submodule.resolve(),
        ): command_result(
            git_revision,
            stdout=f"{GAZEBO_MODELS_REVISION}\n",
        ),
        (
            git_status,
            submodule.resolve(),
        ): command_result(
            git_status,
            stdout="",
        ),
        (gazebo_version, None): command_result(
            gazebo_version,
            stdout="Gazebo Sim, version 8.15.0\n",
        ),
        (make_version, None): command_result(
            make_version,
            stdout="GNU Make 3.81\n",
        ),
        (
            px4_python_imports,
            repository,
        ): command_result(
            px4_python_imports,
        ),
    }

    return repository, responses


def checks_by_id(result):
    return {
        check.check_id: check
        for check in result.checks
    }


def test_matching_environment_passes_preflight(
    tmp_path: Path,
) -> None:
    repository, responses = compatible_environment(
        tmp_path
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    assert result.passed is True
    assert len(result.checks) == 10
    assert all(check.passed for check in result.checks)


def test_revision_mismatches_are_reported(
    tmp_path: Path,
) -> None:
    repository, base_responses = (
        compatible_environment(tmp_path)
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    revision_command = (
        "git",
        "rev-parse",
        "HEAD",
    )
    submodule = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
    ).resolve()

    mismatch_cases = (
        (
            (revision_command, repository),
            "px4_revision_matches",
        ),
        (
            (revision_command, submodule),
            "gazebo_models_revision_matches",
        ),
    )

    for response_key, check_id in mismatch_cases:
        responses = dict(base_responses)
        responses[response_key] = command_result(
            revision_command,
            stdout=f"{'f' * 40}\n",
        )

        result = preflight_environment(
            environment,
            px4_repository=repository,
            runner=FakeRunner(responses),
        )

        checks = checks_by_id(result)

        assert result.passed is False
        assert checks[check_id].passed is False


def test_dirty_worktrees_are_reported(
    tmp_path: Path,
) -> None:
    repository, base_responses = (
        compatible_environment(tmp_path)
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    status_command = (
        "git",
        "status",
        "--porcelain",
    )
    submodule = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
    ).resolve()

    dirty_cases = (
        (
            (status_command, repository),
            "px4_worktree_clean",
        ),
        (
            (status_command, submodule),
            "gazebo_models_worktree_clean",
        ),
    )

    for response_key, check_id in dirty_cases:
        responses = dict(base_responses)
        responses[response_key] = command_result(
            status_command,
            stdout=" M modified-file\n",
        )

        result = preflight_environment(
            environment,
            px4_repository=repository,
            runner=FakeRunner(responses),
        )

        checks = checks_by_id(result)

        assert result.passed is False
        assert checks[check_id].passed is False
        assert "modified-file" in (
            checks[check_id].observed
        )


def test_wrong_gazebo_version_is_reported(
    tmp_path: Path,
) -> None:
    repository, responses = compatible_environment(
        tmp_path
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    gazebo_command = (
        "gz",
        "sim",
        "--version",
    )
    responses[(gazebo_command, None)] = command_result(
        gazebo_command,
        stdout="Gazebo Sim, version 9.0.0\n",
    )

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    checks = checks_by_id(result)

    assert result.passed is False
    assert (
        checks["gazebo_version_matches"].passed
        is False
    )


def test_missing_repository_is_reported(
    tmp_path: Path,
) -> None:
    repository = (
        tmp_path / "missing-PX4-Autopilot"
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    responses = {
        (
            ("gz", "sim", "--version"),
            None,
        ): command_result(
            ("gz", "sim", "--version"),
            stdout="Gazebo Sim, version 8.15.0\n",
        ),
        (
            ("make", "--version"),
            None,
        ): command_result(
            ("make", "--version"),
            stdout="GNU Make 3.81\n",
        ),
    }

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    checks = checks_by_id(result)

    assert result.passed is False
    assert (
        checks["px4_repository_exists"].passed
        is False
    )
    assert (
        checks[
            "gazebo_models_directory_exists"
        ].passed
        is False
    )


def test_missing_make_is_reported(
    tmp_path: Path,
) -> None:
    repository, responses = compatible_environment(
        tmp_path
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    make_command = (
        "make",
        "--version",
    )
    responses[(make_command, None)] = command_result(
        make_command,
        returncode=127,
        stderr="make not found",
    )

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    checks = checks_by_id(result)

    assert result.passed is False
    assert checks["make_available"].passed is False
    assert "make not found" in (
        checks["make_available"].observed
    )

def test_missing_px4_python_is_reported(
    tmp_path: Path,
) -> None:
    repository, responses = (
        compatible_environment(tmp_path)
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    px4_python = (
        repository
        / ".venv"
        / "bin"
        / "python"
    )
    px4_python.unlink()

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    checks = checks_by_id(result)

    assert result.passed is False
    assert (
        checks["px4_python_exists"].passed
        is False
    )
    assert (
        "px4_python_dependencies"
        not in checks
    )


def test_broken_px4_python_dependencies_are_reported(
    tmp_path: Path,
) -> None:
    repository, responses = (
        compatible_environment(tmp_path)
    )
    environment = load_environment_profile(
        PROFILE_PATH
    )

    px4_python = (
        repository
        / ".venv"
        / "bin"
        / "python"
    )
    import_command = (
        str(px4_python),
        "-c",
        (
            "import kconfiglib; "
            "import menuconfig"
        ),
    )

    responses[
        (import_command, repository)
    ] = command_result(
        import_command,
        returncode=1,
        stderr=(
            "ModuleNotFoundError: "
            "No module named 'menuconfig'"
        ),
    )

    result = preflight_environment(
        environment,
        px4_repository=repository,
        runner=FakeRunner(responses),
    )

    checks = checks_by_id(result)

    assert result.passed is False
    assert (
        checks[
            "px4_python_dependencies"
        ].passed
        is False
    )
    assert "ModuleNotFoundError" in (
        checks[
            "px4_python_dependencies"
        ].observed
    )