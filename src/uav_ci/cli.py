# command line interface for UAV-CI

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from uav_ci.scenario.loader import (
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

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())