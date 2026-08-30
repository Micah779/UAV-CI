# run lifecyle, isolation, and logging support

from uav_ci.runtime.manifest import (
    build_run_manifest,
    detect_harness_provenance,
    write_run_manifest,
)
from uav_ci.runtime.result_writer import (
    write_run_result,
)
from uav_ci.runtime.run_directory import (
    RunDirectory,
    create_run_directory,
)
from uav_ci.runtime.preflight import (
    CommandResult,
    EnvironmentPreflightResult,
    PreflightCheckResult,
    preflight_environment,
    run_command,
    CommandRunner,
)
from uav_ci.runtime.logging import (
    LogAttribute,
    StructuredEvent,
    append_event,
)
from uav_ci.runtime.process import (
    ManagedProcess,
    ProcessSpec,
    start_managed_process,
    stop_managed_process,
    wait_managed_process,
    ProcessExitedBeforeReady,
    ProcessReadinessTimeout,
    ReadinessMatch,
    wait_for_process_readiness,
)
from uav_ci.runtime.prepare import (
    InputSnapshots,
    PreparedRun,
    prepare_run,
    snapshot_run_inputs,
)
from uav_ci.runtime.launch import (
    LaunchCheckResult,
    LaunchRejected,
    RunningEnvironment,
    managed_environment,
    run_launch_check,
)
from uav_ci.runtime.health import (
    HealthCheckResult,
    run_health_check,
)
from uav_ci.runtime.flight import (
    FlightCheckResult,
    FlightRejected,
    run_flight_check,
)

__all__ = [
    "RunDirectory",
    "build_run_manifest",
    "create_run_directory",
    "detect_harness_provenance",
    "write_run_manifest",
    "CommandResult",
    "EnvironmentPreflightResult",
    "PreflightCheckResult",
    "preflight_environment",
    "run_command",
    "LogAttribute",
    "StructuredEvent",
    "append_event",
    "ManagedProcess",
    "ProcessSpec",
    "start_managed_process",
    "stop_managed_process",
    "wait_managed_process",
    "ProcessExitedBeforeReady",
    "ProcessReadinessTimeout",
    "ReadinessMatch",
    "wait_for_process_readiness",
    "InputSnapshots",
    "PreparedRun",
    "prepare_run",
    "snapshot_run_inputs",
    "CommandRunner",
    "LaunchCheckResult",
    "LaunchRejected",
    "RunningEnvironment",
    "managed_environment",
    "run_launch_check",
    "HealthCheckResult",
    "run_health_check",
    "FlightCheckResult",
    "FlightRejected",
    "run_flight_check",
    "write_run_result",
]