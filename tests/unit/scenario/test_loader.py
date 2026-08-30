# tests for safe scenario loading and deterministic hashing

from pathlib import Path
import json
from hashlib import sha256
import pytest

from uav_ci.scenario import (
    ScenarioLoadError,
    load_scenario,
)


VALID_SCENARIO_YAML = """
schema_version: 1
scenario_id: baseline_mission
title: Baseline Mission
description: Execute the known nominal X500 mission.

environment:
  profile: px4-gz-x500-v1

mission:
  file: missions/baseline.plan

stimulus:
  type: none

assertions:
  - assertion_id: vehicle_landed
    layer: outcome
    source: ulog
    signal: vehicle_land_detected.landed
    operator: equal
    expected: true
    description: The vehicle reaches a landed state.
""".strip()

def write_valid_mission(
    tmp_path: Path,
    *,
    altitude: float = 20.0,
) -> Path:
    mission_directory = tmp_path / "missions"
    mission_directory.mkdir(exist_ok=True)

    path = mission_directory / "baseline.plan"
    contents = {
        "fileType": "Plan",
        "groundStation": "QGroundControl",
        "mission": {
            "items": [
                {
                    "command": 22,
                    "params": [
                        0,
                        0,
                        0,
                        None,
                        47.3977,
                        8.5456,
                        altitude,
                    ],
                },
            ],
        },
    }
    path.write_text(
        json.dumps(contents),
        encoding="utf-8",
    )
    return path

def write_scenario(
    tmp_path: Path,
    name: str,
    contents: str,
) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def test_valid_yaml_is_loaded_and_hashed(
    tmp_path: Path,
) -> None:
    write_valid_mission(tmp_path)

    path = write_scenario(
        tmp_path,
        "baseline.yaml",
        VALID_SCENARIO_YAML,
    )

    loaded = load_scenario(path)

    assert loaded.source_path == path.resolve()
    assert loaded.scenario.scenario_id == "baseline_mission"
    assert len(loaded.scenario_hash) == 64
    assert set(loaded.scenario_hash) <= set(
        "0123456789abcdef"
    )
    mission_path = (
        tmp_path / "missions/baseline.plan"
    )

    assert loaded.mission_path == (
        mission_path.resolve()
    )
    assert loaded.mission_hash == sha256(
        mission_path.read_bytes()
    ).hexdigest()
    assert loaded.mission_contents == (
        mission_path.read_bytes()
    )


def test_formatting_and_comments_do_not_change_hash(
    tmp_path: Path,
) -> None:
    write_valid_mission(tmp_path)

    first_path = write_scenario(
        tmp_path,
        "first.yaml",
        VALID_SCENARIO_YAML,
    )
    second_path = write_scenario(
        tmp_path,
        "second.yaml",
        (
            "# This comment does not change the scenario.\n\n"
            f"{VALID_SCENARIO_YAML}\n"
        ),
    )

    first = load_scenario(first_path)
    second = load_scenario(second_path)

    assert first.scenario_hash == second.scenario_hash


def test_semantic_change_changes_hash(
    tmp_path: Path,
) -> None:
    write_valid_mission(tmp_path)

    original_path = write_scenario(
        tmp_path,
        "original.yaml",
        VALID_SCENARIO_YAML,
    )
    changed_path = write_scenario(
        tmp_path,
        "changed.yaml",
        VALID_SCENARIO_YAML.replace(
            "Baseline Mission",
            "Updated Baseline Mission",
        ),
    )

    original = load_scenario(original_path)
    changed = load_scenario(changed_path)

    assert original.scenario_hash != changed.scenario_hash


def test_malformed_yaml_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "malformed.yaml",
        "schema_version: [",
    )

    with pytest.raises(
        ScenarioLoadError,
        match="invalid YAML",
    ):
        load_scenario(path)


def test_non_mapping_yaml_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "list.yaml",
        "- first\n- second\n",
    )

    with pytest.raises(
        ScenarioLoadError,
        match="root must be a mapping",
    ):
        load_scenario(path)


def test_invalid_scenario_model_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "unsupported.yaml",
        VALID_SCENARIO_YAML.replace(
            "px4-gz-x500-v1",
            "px4-gz-iris-v1",
        ),
    )

    with pytest.raises(
        ScenarioLoadError,
        match="scenario validation failed",
    ):
        load_scenario(path)


def test_unsafe_yaml_constructor_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "unsafe.yaml",
        (
            "!!python/object/apply:os.system "
            "['echo unsafe']"
        ),
    )

    with pytest.raises(
        ScenarioLoadError,
        match="invalid YAML",
    ):
        load_scenario(path)


def test_non_yaml_extension_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "baseline.txt",
        VALID_SCENARIO_YAML,
    )

    with pytest.raises(
        ScenarioLoadError,
        match=r"\.yaml extension",
    ):
        load_scenario(path)


def test_missing_file_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(
        ScenarioLoadError,
        match="could not read scenario",
    ):
        load_scenario(path)

def test_missing_referenced_mission_is_rejected(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "baseline.yaml",
        VALID_SCENARIO_YAML,
    )

    with pytest.raises(
        ScenarioLoadError,
        match="could not read referenced mission",
    ):
        load_scenario(path)


def test_invalid_mission_json_is_rejected(
    tmp_path: Path,
) -> None:
    mission_directory = tmp_path / "missions"
    mission_directory.mkdir()
    (
        mission_directory / "baseline.plan"
    ).write_text(
        "{invalid",
        encoding="utf-8",
    )

    path = write_scenario(
        tmp_path,
        "baseline.yaml",
        VALID_SCENARIO_YAML,
    )

    with pytest.raises(
        ScenarioLoadError,
        match="invalid mission JSON",
    ):
        load_scenario(path)


def test_mission_change_has_separate_identity(
    tmp_path: Path,
) -> None:
    path = write_scenario(
        tmp_path,
        "baseline.yaml",
        VALID_SCENARIO_YAML,
    )

    write_valid_mission(
        tmp_path,
        altitude=20.0,
    )
    first = load_scenario(path)

    write_valid_mission(
        tmp_path,
        altitude=25.0,
    )
    second = load_scenario(path)

    assert (
        first.scenario_hash
        == second.scenario_hash
    )
    assert (
        first.mission_hash
        != second.mission_hash
    )