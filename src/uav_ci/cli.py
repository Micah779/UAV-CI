# command line interface for UAV-CI

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys
import asyncio

from uav_ci.environment import (
    EnvironmentLoadError,
    load_environment_profile,
)
from uav_ci.runtime import preflight_environment
from uav_ci.scenario import (
    ScenarioLoadError,
    load_scenario,
)
from uav_ci.runtime import (
    LaunchRejected,
    ProcessExitedBeforeReady,
    ProcessReadinessTimeout,
    preflight_environment,
    prepare_run,
    run_launch_check,
    run_health_check,
)
from uav_ci.vehicle import (
    VehicleConnectionError,
    connect_vehicle,
    VehiclePreconditionError,
    MissionExecutionError,
)
from uav_ci.runtime import (
    FlightRejected,
    ULogCaptureError,
    run_flight_check,
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

    prepare_parser = subcommands.add_parser(
        "prepare",
        help=(
            "prepare and verify a run without "
            "launching PX4"
        ),
    )
    prepare_parser.add_argument(
        "scenario",
        type=Path,
        help="path to the scenario YAML",
    )
    prepare_parser.add_argument(
        "--environment",
        type=Path,
        required=True,
        help="path to the environment profile YAML",
    )
    prepare_parser.add_argument(
        "--px4-repository",
        type=Path,
        required=True,
        help="path to the PX4-Autopilot checkout",
    )
    prepare_parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("artifacts/runs"),
        help="directory where run artifacts are stored",
    )
    prepare_parser.add_argument(
        "--repetition-index",
        type=int,
        default=1,
        help="one-based scenario repetition index",
    )

    connect_parser = subcommands.add_parser(
        "connect-check",
        help=(
            "prove MAVSDK connectivity to an "
            "already-running vehicle"
        ),
    )
    connect_parser.add_argument(
        "environment",
        type=Path,
        help="path to the environment profile YAML",
    )
    connect_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help=(
            "maximum time to wait for MAVSDK "
            "vehicle discovery"
        ),
    )

    launch_parser = subcommands.add_parser(
        "launch-check",
        help=(
            "prepare, launch, connect, and safely "
            "stop the supported SITL environment"
        ),
    )
    launch_parser.add_argument(
        "scenario",
        type=Path,
        help="path to the scenario YAML",
    )
    launch_parser.add_argument(
        "--environment",
        type=Path,
        required=True,
        help="path to the environment profile YAML",
    )
    launch_parser.add_argument(
        "--px4-repository",
        type=Path,
        required=True,
        help="path to the PX4-Autopilot checkout",
    )
    launch_parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("artifacts/runs"),
        help="directory where artifacts are stored",
    )
    launch_parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=120.0,
        help="maximum time for PX4 startup",
    )
    launch_parser.add_argument(
        "--connection-timeout-seconds",
        type=float,
        default=30.0,
        help="maximum time for MAVSDK discovery",
    )
    health_parser = subcommands.add_parser(
        "health-check",
        help=(
            "launch SITL and prove safe vehicle "
            "preconditions without arming"
        ),
    )
    health_parser.add_argument(
        "scenario",
        type=Path,
        help="path to the scenario YAML",
    )
    health_parser.add_argument(
        "--environment",
        type=Path,
        required=True,
        help="path to the environment profile YAML",
    )
    health_parser.add_argument(
        "--px4-repository",
        type=Path,
        required=True,
        help="path to the PX4-Autopilot checkout",
    )
    health_parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("artifacts/runs"),
        help="directory where artifacts are stored",
    )
    health_parser.add_argument(
        "--health-timeout-seconds",
        type=float,
        default=60.0,
        help="maximum time to prove preconditions",
    )
    flight_parser = subcommands.add_parser(
        "flight-check",
        help=(
            "execute the snapshotted baseline "
            "mission in the supported SITL profile"
        ),
    )
    flight_parser.add_argument(
        "scenario",
        type=Path,
    )
    flight_parser.add_argument(
        "--environment",
        type=Path,
        required=True,
    )
    flight_parser.add_argument(
        "--px4-repository",
        type=Path,
        required=True,
    )
    flight_parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("artifacts/runs"),
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
    print(f"mission: {loaded.mission_path}")
    print(f"mission_hash: {loaded.mission_hash}")

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

def prepare_run_command(
    scenario_path: Path,
    environment_path: Path,
    px4_repository: Path,
    runs_root: Path,
    repetition_index: int,
) -> int:
    # prepare a run and report whether it may launch

    try:
        prepared = prepare_run(
            scenario_path,
            environment_path,
            px4_repository=px4_repository,
            runs_root=runs_root,
            repetition_index=repetition_index,
        )
    except (
        ScenarioLoadError,
        EnvironmentLoadError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"PREPARATION ERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"PREPARED: {prepared.manifest.scenario_id}"
    )
    print(
        f"run_directory: "
        f"{prepared.run_directory.root}"
    )
    print(
        f"manifest: "
        f"{prepared.run_directory.manifest_path}"
    )
    print(
        f"preflight: "
        f"{prepared.run_directory.preflight_path}"
    )
    print(
        f"ready: {str(prepared.ready).lower()}"
    )

    return 0 if prepared.ready else 1

def connect_vehicle_command(
    environment_path: Path,
    timeout_s: float,
) -> int:
    # prove connectivity without commanding the vehicle

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

    system_address = (
        loaded_environment
        .profile
        .mavsdk
        .system_address
    )

    try:
        connected = asyncio.run(
            connect_vehicle(
                system_address,
                timeout_s=timeout_s,
            )
        )
    except (
        VehicleConnectionError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"CONNECTION FAILED: {exc}",
            file=sys.stderr,
        )
        return 1

    print("CONNECTION PROVED")
    print(f"system_address: {system_address}")
    print(
        "elapsed_seconds: "
        f"{connected.elapsed_s:.3f}"
    )

    return 0

def launch_check_command(
    scenario_path: Path,
    environment_path: Path,
    px4_repository: Path,
    runs_root: Path,
    startup_timeout_s: float,
    connection_timeout_s: float,
) -> int:
    # prepare and prove the complete launch lifecycle

    try:
        prepared = prepare_run(
            scenario_path,
            environment_path,
            px4_repository=px4_repository,
            runs_root=runs_root,
        )
    except (
        ScenarioLoadError,
        EnvironmentLoadError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"PREPARATION ERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    if not prepared.ready:
        print(
            "LAUNCH REJECTED: environment "
            "preflight failed",
            file=sys.stderr,
        )
        print(
            f"run_directory: "
            f"{prepared.run_directory.root}",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(
            run_launch_check(
                prepared,
                px4_repository=px4_repository,
                startup_timeout_s=(
                    startup_timeout_s
                ),
                connection_timeout_s=(
                    connection_timeout_s
                ),
            )
        )
    except (
        LaunchRejected,
        ProcessExitedBeforeReady,
        ProcessReadinessTimeout,
        VehicleConnectionError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"LAUNCH CHECK FAILED: {exc}",
            file=sys.stderr,
        )
        print(
            f"run_directory: "
            f"{prepared.run_directory.root}",
            file=sys.stderr,
        )
        return 1

    print("LAUNCH CHECK PASSED")
    print(
        f"run_directory: "
        f"{prepared.run_directory.root}"
    )
    print(
        "startup_elapsed_seconds: "
        f"{result.readiness.elapsed_s:.3f}"
    )
    print(
        "connection_elapsed_seconds: "
        f"{result.connection_elapsed_s:.3f}"
    )
    print(
        "shutdown_returncode: "
        f"{result.shutdown_returncode}"
    )

    return 0

def health_check_command(
    scenario_path: Path,
    environment_path: Path,
    px4_repository: Path,
    runs_root: Path,
    health_timeout_s: float,
) -> int:
    # prove flight preconditions without arming

    try:
        prepared = prepare_run(
            scenario_path,
            environment_path,
            px4_repository=px4_repository,
            runs_root=runs_root,
        )
    except (
        ScenarioLoadError,
        EnvironmentLoadError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"PREPARATION ERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    if not prepared.ready:
        print(
            "HEALTH CHECK REJECTED: environment "
            "preflight failed",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(
            run_health_check(
                prepared,
                px4_repository=px4_repository,
                health_timeout_s=health_timeout_s,
            )
        )
    except (
        LaunchRejected,
        ProcessExitedBeforeReady,
        ProcessReadinessTimeout,
        VehicleConnectionError,
        VehiclePreconditionError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"HEALTH CHECK FAILED: {exc}",
            file=sys.stderr,
        )
        print(
            f"run_directory: "
            f"{prepared.run_directory.root}",
            file=sys.stderr,
        )
        return 1

    preconditions = result.preconditions

    print(
        "HEALTH CHECK "
        + (
            "PASSED"
            if preconditions.passed
            else "NOT READY"
        )
    )
    print(
        f"run_directory: "
        f"{prepared.run_directory.root}"
    )
    print(f"armable: {preconditions.armable}")
    print(f"armed: {preconditions.armed}")
    print(
        f"landed_state: "
        f"{preconditions.landed_state}"
    )
    print(
        f"evidence: "
        f"{prepared.run_directory.vehicle_preconditions_path}"
    )

    return 0 if preconditions.passed else 1

def flight_check_command(
    scenario_path: Path,
    environment_path: Path,
    px4_repository: Path,
    runs_root: Path,
) -> int:
    # execute the first bounded SITL flight

    try:
        prepared = prepare_run(
            scenario_path,
            environment_path,
            px4_repository=px4_repository,
            runs_root=runs_root,
        )
    except (
        ScenarioLoadError,
        EnvironmentLoadError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"PREPARATION ERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    if not prepared.ready:
        print(
            "FLIGHT REJECTED: environment "
            "preflight failed",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(
            run_flight_check(
                prepared,
                px4_repository=px4_repository,
            )
        )
    except (
        FlightRejected,
        LaunchRejected,
        ProcessExitedBeforeReady,
        ProcessReadinessTimeout,
        VehicleConnectionError,
        VehiclePreconditionError,
        MissionExecutionError,
        ULogCaptureError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"FLIGHT CHECK FAILED: {exc}",
            file=sys.stderr,
        )
        print(
            f"run_directory: "
            f"{prepared.run_directory.root}",
            file=sys.stderr,
        )
        return 1

    print("FLIGHT CHECK PASSED")
    print(
        f"run_directory: "
        f"{prepared.run_directory.root}"
    )
    print(
        "mission_items: "
        f"{result.mission.mission_item_count}"
    )
    print(
        "mission_progress: "
        f"{result.mission.final_current}/"
        f"{result.mission.final_total}"
    )
    print(
        "airborne: "
        f"{result.mission.airborne_observed}"
    )
    print(
        "landed: "
        f"{result.mission.landed_observed}"
    )
    print(
        "disarmed: "
        f"{result.mission.disarmed_observed}"
    )
    print(
        "elapsed_seconds: "
        f"{result.mission.elapsed_s:.3f}"
    )
    print(
        f"ulog: {result.ulog.path}"
    )
    print(
        f"ulog_sha256: {result.ulog.sha256}"
    )
    print(
        "ulog_size_bytes: "
        f"{result.ulog.size_bytes}"
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

    if arguments.command == "preflight":
        return preflight_environment_command(
            arguments.environment,
            arguments.px4_repository,
        )

    if arguments.command == "prepare":
        return prepare_run_command(
            arguments.scenario,
            arguments.environment,
            arguments.px4_repository,
            arguments.runs_root,
            arguments.repetition_index,
        )

    if arguments.command == "connect-check":
        return connect_vehicle_command(
            arguments.environment,
            arguments.timeout_seconds,
        )

    if arguments.command == "launch-check":
        return launch_check_command(
            arguments.scenario,
            arguments.environment,
            arguments.px4_repository,
            arguments.runs_root,
            arguments.startup_timeout_seconds,
            arguments.connection_timeout_seconds,
        )
    if arguments.command == "health-check":
        return health_check_command(
            arguments.scenario,
            arguments.environment,
            arguments.px4_repository,
            arguments.runs_root,
            arguments.health_timeout_seconds,
        )
    if arguments.command == "flight-check":
        return flight_check_command(
            arguments.scenario,
            arguments.environment,
            arguments.px4_repository,
            arguments.runs_root,
        )

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())