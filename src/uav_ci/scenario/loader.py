# load, validate, and fingerprint YAML scenarios

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from pydantic import ValidationError
import yaml

from uav_ci.domain.scenario import ScenarioSpec
from uav_ci.scenario.errors import ScenarioLoadError


@dataclass(frozen=True, slots=True)
class LoadedScenario:
    # validated scenario and referenced mission identity

    source_path: Path
    scenario: ScenarioSpec
    scenario_hash: str

    mission_path: Path
    mission_hash: str
    mission_contents: bytes


def calculate_scenario_hash(
    scenario: ScenarioSpec,
) -> str:
    # calculate a deterministic hash of validated scenario data

    canonical_json = json.dumps(
        scenario.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

def calculate_mission_hash(
    contents: bytes,
) -> str:
    # identify the exact mission file bytes

    return sha256(contents).hexdigest()

def load_scenario(path: str | Path) -> LoadedScenario:
    # read, validate, and fingerprint one YAML scenario

    source_path = Path(path).resolve()

    if source_path.suffix.lower() != ".yaml":
        raise ScenarioLoadError(
            "scenario files must use the .yaml extension: "
            f"{source_path}"
        )

    try:
        text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ScenarioLoadError(
            f"could not read scenario {source_path}: {exc}"
        ) from exc

    try:
        raw_data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioLoadError(
            f"invalid YAML in {source_path}: {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise ScenarioLoadError(
            "scenario root must be a mapping: "
            f"{source_path}"
        )

    try:
        scenario = ScenarioSpec.model_validate(raw_data)
    except ValidationError as exc:
        raise ScenarioLoadError(
            "scenario validation failed for "
            f"{source_path}: {exc}"
        ) from exc

    if source_path.parent.name == "scenarios":
        project_root = source_path.parent.parent
    else:
        # Supports isolated tests and embedded users.
        project_root = source_path.parent

    mission_path = (
        project_root / scenario.mission.file
    ).resolve()

    try:
        mission_contents = mission_path.read_bytes()
    except OSError as exc:
        raise ScenarioLoadError(
            "could not read referenced mission "
            f"{mission_path}: {exc}"
        ) from exc

    _validate_qgroundcontrol_plan(
        mission_contents,
        path=mission_path,
    )

    return LoadedScenario(
        source_path=source_path,
        scenario=scenario,
        scenario_hash=calculate_scenario_hash(
            scenario
        ),
        mission_path=mission_path,
        mission_hash=calculate_mission_hash(
            mission_contents
        ),
        mission_contents=mission_contents,
    )

def _validate_qgroundcontrol_plan(
    contents: bytes,
    *,
    path: Path,
) -> None:
    # verify the minimum QGC plan structure we consume

    try:
        raw_plan = json.loads(contents)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ScenarioLoadError(
            f"invalid mission JSON in {path}: {exc}"
        ) from exc

    if not isinstance(raw_plan, dict):
        raise ScenarioLoadError(
            "mission root must be a mapping: "
            f"{path}"
        )

    if raw_plan.get("fileType") != "Plan":
        raise ScenarioLoadError(
            "mission fileType must be 'Plan': "
            f"{path}"
        )

    if (
        raw_plan.get("groundStation")
        != "QGroundControl"
    ):
        raise ScenarioLoadError(
            "mission must be a QGroundControl plan: "
            f"{path}"
        )

    mission = raw_plan.get("mission")

    if not isinstance(mission, dict):
        raise ScenarioLoadError(
            "mission plan must contain a mission "
            f"mapping: {path}"
        )

    items = mission.get("items")

    if (
        not isinstance(items, list)
        or not items
    ):
        raise ScenarioLoadError(
            "mission plan must contain at least "
            f"one mission item: {path}"
        )