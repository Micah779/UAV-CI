# tests for MAVSDK vehicle connection handling

import asyncio

import pytest

from uav_ci.vehicle import (
    VehicleConnectionError,
    VehicleConnectionStreamEnded,
    VehicleConnectionTimeout,
    connect_vehicle,
)


class FakeConnectionState:
    def __init__(
        self,
        *,
        is_connected: bool,
    ) -> None:
        self.is_connected = is_connected


class FakeCore:
    def __init__(
        self,
        states: tuple[FakeConnectionState, ...],
    ) -> None:
        self.states = states

    async def connection_state(self):
        for state in self.states:
            await asyncio.sleep(0)
            yield state


class NeverConnectingCore:
    async def connection_state(self):
        while True:
            await asyncio.sleep(60)

            if False:
                yield FakeConnectionState(
                    is_connected=False,
                )


class FakeSystem:
    def __init__(self, core) -> None:
        self.core = core
        self.connected_address: str | None = None

    async def connect(
        self,
        *,
        system_address: str,
    ) -> None:
        self.connected_address = system_address


class FailingSystem(FakeSystem):
    async def connect(
        self,
        *,
        system_address: str,
    ) -> None:
        raise RuntimeError(
            "test backend failure"
        )


def test_connected_state_proves_vehicle_connection(
) -> None:
    system = FakeSystem(
        FakeCore(
            (
                FakeConnectionState(
                    is_connected=False,
                ),
                FakeConnectionState(
                    is_connected=True,
                ),
            )
        )
    )

    clock_values = iter((10.0, 10.25))

    connected = asyncio.run(
        connect_vehicle(
            "udpin://0.0.0.0:14540",
            timeout_s=1,
            system_factory=lambda: system,
            monotonic_clock=lambda: next(
                clock_values
            ),
        )
    )

    assert connected.system is system
    assert connected.system_address == (
        "udpin://0.0.0.0:14540"
    )
    assert connected.elapsed_s == 0.25
    assert system.connected_address == (
        "udpin://0.0.0.0:14540"
    )


def test_ended_state_stream_is_not_connection(
) -> None:
    system = FakeSystem(
        FakeCore(
            (
                FakeConnectionState(
                    is_connected=False,
                ),
            )
        )
    )

    with pytest.raises(
        VehicleConnectionStreamEnded,
        match="before a vehicle was discovered",
    ):
        asyncio.run(
            connect_vehicle(
                "udpin://0.0.0.0:14540",
                timeout_s=1,
                system_factory=lambda: system,
            )
        )


def test_connection_timeout_is_bounded() -> None:
    system = FakeSystem(
        NeverConnectingCore()
    )

    with pytest.raises(
        VehicleConnectionTimeout,
        match="within 0.01 seconds",
    ):
        asyncio.run(
            connect_vehicle(
                "udpin://0.0.0.0:14540",
                timeout_s=0.01,
                system_factory=lambda: system,
            )
        )


def test_backend_failure_has_connection_context(
) -> None:
    system = FailingSystem(
        FakeCore(())
    )

    with pytest.raises(
        VehicleConnectionError,
        match="MAVSDK connection failed",
    ) as exc_info:
        asyncio.run(
            connect_vehicle(
                "udpin://0.0.0.0:14540",
                timeout_s=1,
                system_factory=lambda: system,
            )
        )

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )


@pytest.mark.parametrize(
    ("system_address", "timeout_s"),
    (
        ("", 1.0),
        ("   ", 1.0),
        ("udpin://0.0.0.0:14540", 0.0),
        ("udpin://0.0.0.0:14540", -1.0),
    ),
)
def test_invalid_connection_arguments_are_rejected(
    system_address: str,
    timeout_s: float,
) -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            connect_vehicle(
                system_address,
                timeout_s=timeout_s,
            )
        )