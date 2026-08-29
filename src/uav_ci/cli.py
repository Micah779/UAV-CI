# command line interface for UAV-CI

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from uav_ci.environment import (
    EnvironmentLoadError,
    load_environment_profile,
)
from uav_ci.runtime import preflight_environment
from uav_ci.scenario import (
    ScenarioLoadError,
    load_scenario,
)


def build_parser() -> argparse.ArgumentParser:
    # build the UAV-CI command line parser

    parser = argparse.ArgumentParser(
        prog="uav-ci",
        description=(
            "Validate and execute PX4 SITL assurance scenarios."
        ),
    )

    subcommands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    validate_parser = subcommands.add_parser(
        "validate",
        help="validate a YAML scenario without running it",
    )
    validate_parser.add_argument(
        "scenario",
        type=Path,
        help="path to the scenario YAML file",
    )

    preflight_parser = subcommands.add_parser(
        "preflight",
        help=(
            "verify the installed PX4 environment "
            "without launching it"
        ),
    )
    preflight_parser.add_argument(
        "environment",
        type=Path,
        help="path to the environment profile YAML",
    )
    preflight_parser.add_argument(
        "--px4-repository",
        type=Path,
        required=True,
        help="path to the PX4-Autopilot checkout",
    )

    return parser

def validate_scenario_command(path: Path) -> int:
    # validate one scenario and print its identity

    try:
        loaded = load_scenario(path)
    except ScenarioLoadError as exc:
        print(
            f"INVALID: {exc}",
            file=sys.stderr,
        )
        return 1

    activation_required = str(
        loaded.scenario.requires_activation
    ).lower()

    print(f"VALID: {loaded.scenario.scenario_id}")
    print(f"source: {loaded.source_path}")
    print(f"hash: {loaded.scenario_hash}")
    print(
        "activation_required: "
        f"{activation_required}"
    )
    print(
        f"assertions: {len(loaded.scenario.assertions)}"
    )

    return 0

def preflight_environment_command(
    environment_path: Path,
    px4_repository: Path,
) -> int:
    # verify the installed environment and print checks

    try:
        loaded_environment = (
            load_environment_profile(
                environment_path
            )
        )
    except EnvironmentLoadError as exc:
        print(
            f"INVALID ENVIRONMENT: {exc}",
            file=sys.stderr,
        )
        return 1

    result = preflight_environment(
        loaded_environment,
        px4_repository=px4_repository,
    )

    print(f"profile: {result.profile_id}")
    print(f"hash: {result.profile_hash}")
    print(f"px4_repository: {result.px4_repository}")

    for check in result.checks:
        label = "PASS" if check.passed else "FAIL"
        print(
            f"[{label}] {check.check_id}: "
            f"expected={check.expected!r}, "
            f"observed={check.observed!r}"
        )

    if result.passed:
        print("PREFLIGHT PASSED")
        return 0

    print("PREFLIGHT FAILED")
    return 1


def main(
    argv: Sequence[str] | None = None,
) -> int:
    # run the UAV-CI command-line interface

    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "validate":
        return validate_scenario_command(
            arguments.scenario
        )

    if arguments.command == "preflight":
        return preflight_environment_command(
            arguments.environment,
            arguments.px4_repository,
        )

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())