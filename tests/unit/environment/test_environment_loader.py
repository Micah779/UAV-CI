# tests for trusted environment-profile loading

from pathlib import Path

import pytest

from uav_ci.environment import (
    EnvironmentLoadError,
    load_environment_profile,
)


PROJECT_ROOT = Path(__file__).parents[3]
PROFILE_PATH = (
    PROJECT_ROOT
    / "environments"
    / "px4-gz-x500-v1.yaml"
)
PATCH_PATH = (
    PROJECT_ROOT
    / "environments"
    / "patches"
    / "x500-enable-wind.patch"
)

PROFILE_TEXT = PROFILE_PATH.read_text(
    encoding="utf-8"
)
PATCH_BYTES = PATCH_PATH.read_bytes()


def write_environment_tree(
    root: Path,
    *,
    profile_text: str = PROFILE_TEXT,
    patch_bytes: bytes = PATCH_BYTES,
) -> Path:
    environment_directory = root / "environments"
    patch_directory = (
        environment_directory / "patches"
    )

    patch_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    profile_path = (
        environment_directory
        / "px4-gz-x500-v1.yaml"
    )
    patch_path = (
        patch_directory
        / "x500-enable-wind.patch"
    )

    profile_path.write_text(
        profile_text,
        encoding="utf-8",
    )
    patch_path.write_bytes(patch_bytes)

    return profile_path


def test_known_environment_is_loaded_and_hashed() -> None:
    loaded = load_environment_profile(
        PROFILE_PATH
    )

    assert loaded.source_path == PROFILE_PATH.resolve()
    assert loaded.repository_root == (
        PROJECT_ROOT.resolve()
    )
    assert loaded.profile.profile_id == (
        "px4-gz-x500-v1"
    )
    assert loaded.patch_paths == (
        PATCH_PATH.resolve(),
    )
    assert len(loaded.profile_hash) == 64
    assert set(loaded.profile_hash) <= set(
        "0123456789abcdef"
    )


def test_comments_do_not_change_environment_hash(
    tmp_path: Path,
) -> None:
    first_path = write_environment_tree(
        tmp_path / "first"
    )
    second_path = write_environment_tree(
        tmp_path / "second",
        profile_text=(
            "# Formatting-only comment.\n\n"
            f"{PROFILE_TEXT}\n"
        ),
    )

    first = load_environment_profile(first_path)
    second = load_environment_profile(second_path)

    assert first.profile_hash == second.profile_hash


def test_semantic_change_changes_environment_hash(
    tmp_path: Path,
) -> None:
    original_path = write_environment_tree(
        tmp_path / "original"
    )
    changed_path = write_environment_tree(
        tmp_path / "changed",
        profile_text=PROFILE_TEXT.replace(
            (
                "Enable Gazebo wind effects on the "
                "X500 base link."
            ),
            (
                "Enable verified Gazebo wind effects "
                "on the X500 base link."
            ),
        ),
    )

    original = load_environment_profile(original_path)
    changed = load_environment_profile(changed_path)

    assert original.profile_hash != changed.profile_hash


def test_invalid_yaml_shapes_are_rejected(
    tmp_path: Path,
) -> None:
    invalid_documents = (
        "schema_version: [",
        "- first\n- second\n",
    )

    for index, document in enumerate(
        invalid_documents
    ):
        environment_directory = (
            tmp_path / str(index) / "environments"
        )
        environment_directory.mkdir(parents=True)

        profile_path = (
            environment_directory
            / "px4-gz-x500-v1.yaml"
        )
        profile_path.write_text(
            document,
            encoding="utf-8",
        )

        with pytest.raises(EnvironmentLoadError):
            load_environment_profile(profile_path)


def test_invalid_environment_model_is_rejected(
    tmp_path: Path,
) -> None:
    profile_path = write_environment_tree(
        tmp_path,
        profile_text=PROFILE_TEXT.replace(
            "profile_id: px4-gz-x500-v1",
            "profile_id: px4-gz-iris-v1",
        ),
    )

    with pytest.raises(
        EnvironmentLoadError,
        match="environment validation failed",
    ):
        load_environment_profile(profile_path)


def test_missing_patch_is_rejected(
    tmp_path: Path,
) -> None:
    profile_path = write_environment_tree(tmp_path)
    patch_path = (
        tmp_path
        / "environments"
        / "patches"
        / "x500-enable-wind.patch"
    )
    patch_path.unlink()

    with pytest.raises(
        EnvironmentLoadError,
        match="could not read environment patch",
    ):
        load_environment_profile(profile_path)


def test_modified_patch_is_rejected(
    tmp_path: Path,
) -> None:
    profile_path = write_environment_tree(
        tmp_path,
        patch_bytes=(
            PATCH_BYTES
            + b"\n# unexpected modification\n"
        ),
    )

    with pytest.raises(
        EnvironmentLoadError,
        match="patch digest mismatch",
    ):
        load_environment_profile(profile_path)


def test_unsafe_yaml_constructor_is_rejected(
    tmp_path: Path,
) -> None:
    environment_directory = (
        tmp_path / "environments"
    )
    environment_directory.mkdir()

    profile_path = (
        environment_directory
        / "px4-gz-x500-v1.yaml"
    )
    profile_path.write_text(
        (
            "!!python/object/apply:os.system "
            "['echo unsafe']"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        EnvironmentLoadError,
        match="invalid YAML",
    ):
        load_environment_profile(profile_path)