# public vehicle integration interfaces

from uav_ci.vehicle.connection import (
    ConnectedVehicle,
    VehicleConnectionError,
    VehicleConnectionStreamEnded,
    VehicleConnectionTimeout,
    VehicleSystem,
    VehicleSystemFactory,
    connect_vehicle,
    create_mavsdk_system,
)

from uav_ci.vehicle.preconditions import (
    VehiclePreconditionError,
    VehiclePreconditionResult,
    VehiclePreconditionStreamEnded,
    VehiclePreconditionTimeout,
    wait_for_vehicle_preconditions,
)

from uav_ci.vehicle.mission import (
    MissionExecutionError,
    MissionExecutionResult,
    MissionExecutionTimeout,
    MissionTelemetryStreamEnded,
    execute_mission,
)


__all__ = [
    "ConnectedVehicle",
    "VehicleConnectionError",
    "VehicleConnectionStreamEnded",
    "VehicleConnectionTimeout",
    "VehicleSystem",
    "VehicleSystemFactory",
    "connect_vehicle",
    "create_mavsdk_system",
    "VehiclePreconditionError",
    "VehiclePreconditionResult",
    "VehiclePreconditionStreamEnded",
    "VehiclePreconditionTimeout",
    "wait_for_vehicle_preconditions",
    "MissionExecutionError",
    "MissionExecutionResult",
    "MissionExecutionTimeout",
    "MissionTelemetryStreamEnded",
    "execute_mission",
]