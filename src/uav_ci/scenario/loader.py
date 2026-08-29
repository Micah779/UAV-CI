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
    # a validated scenario together with its source identity

    source_path: Path
    scenario: ScenarioSpec
    scenario_hash: str


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

    return LoadedScenario(
        source_path=source_path,
        scenario=scenario,
        scenario_hash=calculate_scenario_hash(scenario),
    )