# establish and prove MAVSDK vehicle connections

import asyncio
from collections.abc import (
    AsyncIterator,
    Callable,
)
from dataclasses import dataclass
from time import monotonic
from typing import Protocol, cast


class VehicleConnectionState(Protocol):
    # minimum MAVSDK connection state used by UAV-CI

    @property
    def is_connected(self) -> bool:
        ...

class VehicleCore(Protocol):
    # minimum MAVSDK core interface used by UAV-CI

    def connection_state(
        self,
    ) -> AsyncIterator[VehicleConnectionState]:
        ...


class VehicleSystem(Protocol):
    # minimum MAVSDK system interface used by UAV-CI

    @property
    def core(self) -> VehicleCore:
        ...

    async def connect(
        self,
        *,
        system_address: str,
    ) -> None:
        ...


VehicleSystemFactory = Callable[[], VehicleSystem]


@dataclass(frozen=True, slots=True)
class ConnectedVehicle:
    # proven live connection retained for later operations

    system: VehicleSystem
    system_address: str
    elapsed_s: float


class VehicleConnectionError(RuntimeError):
    # base error for MAVSDK connection failures
    pass


class VehicleConnectionTimeout(
    VehicleConnectionError,
    TimeoutError,
):
    # MAVSDK did not discover a vehicle in time
    pass


class VehicleConnectionStreamEnded(
    VehicleConnectionError,
):
    # MAVSDK stopped reporting before connecting
    pass


def create_mavsdk_system() -> VehicleSystem:
    # construct the production MAVSDK implementation

    from mavsdk import System

    return cast(
        VehicleSystem,
        System(),
    )


async def connect_vehicle(
    system_address: str,
    *,
    timeout_s: float = 30.0,
    system_factory: VehicleSystemFactory = (
        create_mavsdk_system
    ),
    monotonic_clock: Callable[[], float] = monotonic,
) -> ConnectedVehicle:
    # connect and wait for MAVSDK to discover one vehicle

    if not system_address.strip():
        raise ValueError(
            "system_address cannot be empty"
        )

    if timeout_s <= 0:
        raise ValueError(
            "connection timeout must be positive"
        )

    try:
        system = system_factory()
    except Exception as exc:
        raise VehicleConnectionError(
            "failed to create the MAVSDK system"
        ) from exc

    started = monotonic_clock()

    async def connect_and_observe(
    ) -> VehicleConnectionState:
        await system.connect(
            system_address=system_address
        )

        async for state in (
            system.core.connection_state()
        ):
            if state.is_connected:
                return state

        raise VehicleConnectionStreamEnded(
            "MAVSDK connection-state stream ended "
            "before a vehicle was discovered"
        )

    try:
        state = await asyncio.wait_for(
            connect_and_observe(),
            timeout=timeout_s,
        )
    except TimeoutError as exc:
        raise VehicleConnectionTimeout(
            "MAVSDK did not discover a vehicle at "
            f"{system_address!r} within "
            f"{timeout_s} seconds"
        ) from exc
    except VehicleConnectionError:
        raise
    except Exception as exc:
        raise VehicleConnectionError(
            "MAVSDK connection failed for "
            f"{system_address!r}: {exc}"
        ) from exc

    return ConnectedVehicle(
        system=system,
        system_address=system_address,
        elapsed_s=monotonic_clock() - started,
    )