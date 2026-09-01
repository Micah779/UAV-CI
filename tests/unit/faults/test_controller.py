# tests for activation-first fault lifecycles

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from uav_ci.domain.enums import (
    ClockDomain,
    EvidenceSource,
)
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.scenario import FaultType
from uav_ci.faults import (
    FaultActivationNotProven,
    FaultActivationResult,
    FaultLifecycle,
    FaultLifecycleError,
)


def activation_evidence() -> EvidenceRef:
    return EvidenceRef(
        source=EvidenceSource.SIMULATOR,
        clock_domain=(
            ClockDomain.HOST_MONOTONIC
        ),
        timestamp_us=1_000_000,
        signal="gazebo.wind.velocity",
        artifact_path=Path(
            "evidence/fault_activation.json"
        ),
        description=(
            "Gazebo reported the configured "
            "wind velocity."
        ),
    )


class FakeFaultController:
    def __init__(
        self,
        *,
        fault_type: FaultType = "wind",
        activated: bool = True,
    ) -> None:
        self._fault_type = fault_type
        self._activated = activated
        self.calls: list[str] = []

    @property
    def fault_type(self) -> FaultType:
        return self._fault_type

    async def prepare(self) -> None:
        self.calls.append("prepare")

    async def activate(self) -> None:
        self.calls.append("activate")

    async def prove_activation(
        self,
    ) -> FaultActivationResult:
        self.calls.append("prove_activation")

        return FaultActivationResult(
            fault_type=self.fault_type,
            activated=self._activated,
            evidence=(
                (activation_evidence(),)
                if self._activated
                else ()
            ),
        )

    async def cleanup(self) -> None:
        self.calls.append("cleanup")


def test_complete_activation_lifecycle() -> None:
    controller = FakeFaultController()
    lifecycle = FaultLifecycle(controller)

    async def run() -> None:
        await lifecycle.prepare()
        await lifecycle.activate()

        result = (
            await lifecycle.prove_activation()
        )

        assert result.activated is True
        assert lifecycle.activation_proven is True
        assert (
            lifecycle.require_activation_proven()
            is result
        )

        await lifecycle.cleanup()

    asyncio.run(run())

    assert controller.calls == [
        "prepare",
        "activate",
        "prove_activation",
        "cleanup",
    ]
    assert lifecycle.cleaned is True


def test_activation_requires_preparation() -> None:
    controller = FakeFaultController()
    lifecycle = FaultLifecycle(controller)

    with pytest.raises(
        FaultLifecycleError,
        match="prepared",
    ):
        asyncio.run(lifecycle.activate())

    assert controller.calls == []


def test_proof_requires_activation_request() -> None:
    controller = FakeFaultController()
    lifecycle = FaultLifecycle(controller)

    asyncio.run(lifecycle.prepare())

    with pytest.raises(
        FaultLifecycleError,
        match="activated",
    ):
        asyncio.run(
            lifecycle.prove_activation()
        )

    assert controller.calls == ["prepare"]


def test_unproven_activation_blocks_response() -> None:
    controller = FakeFaultController(
        activated=False,
    )
    lifecycle = FaultLifecycle(controller)

    async def run() -> None:
        await lifecycle.prepare()
        await lifecycle.activate()
        result = (
            await lifecycle.prove_activation()
        )

        assert result.activated is False

    asyncio.run(run())

    with pytest.raises(
        FaultActivationNotProven,
        match="response cannot be evaluated",
    ):
        lifecycle.require_activation_proven()


def test_proven_activation_requires_evidence() -> None:
    with pytest.raises(
        ValidationError,
        match="requires evidence",
    ):
        FaultActivationResult(
            fault_type="wind",
            activated=True,
            evidence=(),
        )


def test_result_must_match_controller_type() -> None:
    controller = FakeFaultController(
        fault_type="wind",
    )
    lifecycle = FaultLifecycle(controller)

    async def wrong_proof():
        return FaultActivationResult(
            fault_type="gnss_loss",
            activated=True,
            evidence=(activation_evidence(),),
        )

    controller.prove_activation = wrong_proof

    async def run() -> None:
        await lifecycle.prepare()
        await lifecycle.activate()
        await lifecycle.prove_activation()

    with pytest.raises(
        FaultLifecycleError,
        match="does not match",
    ):
        asyncio.run(run())


def test_cleanup_is_idempotent() -> None:
    controller = FakeFaultController()
    lifecycle = FaultLifecycle(controller)

    async def run() -> None:
        await lifecycle.cleanup()
        await lifecycle.cleanup()

    asyncio.run(run())

    assert controller.calls == ["cleanup"]
    assert lifecycle.cleaned is True