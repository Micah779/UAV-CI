# load, verify, and fingerprint environment profiles

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from pathlib import Path

from pydantic import ValidationError
import yaml

from uav_ci.domain.environment import EnvironmentProfile
from uav_ci.environment.errors import (
    EnvironmentLoadError,
)


@dataclass(frozen=True, slots=True)
class LoadedEnvironmentProfile:
    """A validated and integrity-checked environment."""

    source_path: Path
    repository_root: Path
    profile: EnvironmentProfile
    profile_hash: str
    patch_paths: tuple[Path, ...]


def calculate_environment_hash(
    profile: EnvironmentProfile,
) -> str:
    # hash the canonical validated environment profile

    canonical_json = json.dumps(
        profile.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def load_environment_profile(
    path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> LoadedEnvironmentProfile:
    # load and verify one environment profile

    source_path = Path(path).resolve()

    if source_path.suffix.lower() != ".yaml":
        raise EnvironmentLoadError(
            "environment profiles must use the "
            f".yaml extension: {source_path}"
        )

    try:
        text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentLoadError(
            "could not read environment profile "
            f"{source_path}: {exc}"
        ) from exc

    try:
        raw_data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EnvironmentLoadError(
            f"invalid YAML in {source_path}: {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise EnvironmentLoadError(
            "environment profile root must be a mapping: "
            f"{source_path}"
        )

    try:
        profile = EnvironmentProfile.model_validate(
            raw_data
        )
    except ValidationError as exc:
        raise EnvironmentLoadError(
            "environment validation failed for "
            f"{source_path}: {exc}"
        ) from exc

    if repository_root is None:
        resolved_repository_root = (
            source_path.parent.parent.resolve()
        )
    else:
        resolved_repository_root = Path(
            repository_root
        ).resolve()

    verified_patch_paths: list[Path] = []

    for patch in profile.patches:
        patch_path = (
            resolved_repository_root / patch.file
        ).resolve()

        try:
            patch_path.relative_to(
                resolved_repository_root
            )
        except ValueError as exc:
            raise EnvironmentLoadError(
                "environment patch resolves outside "
                f"the repository: {patch.file}"
            ) from exc

        try:
            patch_contents = patch_path.read_bytes()
        except OSError as exc:
            raise EnvironmentLoadError(
                f"could not read environment patch "
                f"{patch_path}: {exc}"
            ) from exc

        actual_digest = sha256(
            patch_contents
        ).hexdigest()

        if not hmac.compare_digest(
            actual_digest,
            patch.sha256,
        ):
            raise EnvironmentLoadError(
                "environment patch digest mismatch for "
                f"{patch.file}: expected {patch.sha256}, "
                f"found {actual_digest}"
            )

        verified_patch_paths.append(patch_path)

    return LoadedEnvironmentProfile(
        source_path=source_path,
        repository_root=resolved_repository_root,
        profile=profile,
        profile_hash=calculate_environment_hash(profile),
        patch_paths=tuple(verified_patch_paths),
    )