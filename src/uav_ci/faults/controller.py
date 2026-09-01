# activation-first lifecycle for UAV-CI fault adapters

from typing import (
    Protocol,
    Self,
    runtime_checkable,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    model_validator,
)

from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.scenario import FaultType


class FaultActivationResult(BaseModel):
    # result of independently checking fault activation

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    fault_type: FaultType
    activated: StrictBool
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def activated_fault_requires_evidence(
        self,
    ) -> Self:
        if self.activated and not self.evidence:
            raise ValueError(
                "proven fault activation requires "
                "evidence"
            )

        return self


@runtime_checkable
class FaultController(Protocol):
    # adapter contract implemented by each fault type

    @property
    def fault_type(self) -> FaultType:
        ...

    async def prepare(self) -> None:
        # prepare isolated resources before activation
        ...

    async def activate(self) -> None:
        # request that the fault be applied
        ...

    async def prove_activation(
        self,
    ) -> FaultActivationResult:
        # independently determine whether it activated
        ...

    async def cleanup(self) -> None:
        # release or restore controller-owned resources
        ...


class FaultLifecycleError(RuntimeError):
    # fault-controller lifecycle was used incorrectly
    pass


class FaultActivationNotProven(
    FaultLifecycleError,
):
    # response evaluation was requested without proof
    pass


class FaultLifecycle:
    # enforce ordering around one fault controller

    def __init__(
        self,
        controller: FaultController,
    ) -> None:
        self._controller = controller
        self._prepared = False
        self._activation_requested = False
        self._activation_result: (
            FaultActivationResult | None
        ) = None
        self._cleaned = False

    @property
    def fault_type(self) -> FaultType:
        return self._controller.fault_type

    @property
    def prepared(self) -> bool:
        return self._prepared

    @property
    def activation_requested(self) -> bool:
        return self._activation_requested

    @property
    def activation_result(
        self,
    ) -> FaultActivationResult | None:
        return self._activation_result

    @property
    def activation_proven(self) -> bool:
        return (
            self._activation_result is not None
            and self._activation_result.activated
        )

    @property
    def cleaned(self) -> bool:
        return self._cleaned

    def _require_not_cleaned(self) -> None:
        if self._cleaned:
            raise FaultLifecycleError(
                "fault lifecycle has already "
                "been cleaned"
            )

    async def prepare(self) -> None:
        self._require_not_cleaned()

        if self._prepared:
            raise FaultLifecycleError(
                "fault controller is already prepared"
            )

        await self._controller.prepare()
        self._prepared = True

    async def activate(self) -> None:
        self._require_not_cleaned()

        if not self._prepared:
            raise FaultLifecycleError(
                "fault controller must be prepared "
                "before activation"
            )

        if self._activation_requested:
            raise FaultLifecycleError(
                "fault activation was already requested"
            )

        await self._controller.activate()
        self._activation_requested = True

    async def prove_activation(
        self,
    ) -> FaultActivationResult:
        self._require_not_cleaned()

        if not self._activation_requested:
            raise FaultLifecycleError(
                "fault must be activated before "
                "activation is evaluated"
            )

        if self._activation_result is not None:
            raise FaultLifecycleError(
                "fault activation was already evaluated"
            )

        result = (
            await self
            ._controller
            .prove_activation()
        )

        if result.fault_type != self.fault_type:
            raise FaultLifecycleError(
                "activation result fault type does "
                "not match its controller"
            )

        self._activation_result = result
        return result

    def require_activation_proven(
        self,
    ) -> FaultActivationResult:
        if not self.activation_proven:
            raise FaultActivationNotProven(
                "vehicle response cannot be "
                "evaluated because fault activation "
                "was not proven"
            )

        assert self._activation_result is not None
        return self._activation_result

    async def cleanup(self) -> None:
        if self._cleaned:
            return

        try:
            await self._controller.cleanup()
        finally:
            self._cleaned = True