# one-run wind control; the caller owns the vehicle and simulator

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict
import json
import math
from pathlib import Path
from time import monotonic_ns
from typing import Literal

from uav_ci.domain.enums import ClockDomain, EvidenceSource
from uav_ci.domain.evidence import EvidenceRef
from uav_ci.domain.scenario import WindStimulusSpec
from uav_ci.faults.controller import (
    FaultActivationResult,
    FaultLifecycle,
    FaultLifecycleError,
)
from uav_ci.faults.wind_activation import (
    BASELINE_MAX_AGE_NS,
    WindActivationAssessment,
    evaluate_wind_activation,
)
from uav_ci.faults.wind_command import (
    GazeboWindCommandAdapter,
    WindCommand,
    WindCommandReceipt,
    WindCommandRunner,
    run_gazebo_command,
)
from uav_ci.faults.wind_observer import (
    RecordedWindObservation,
    WindObservationTimeout,
    observe_wind,
)
from uav_ci.runtime.files import publish_text_exclusively


class GazeboWindController:
    def __init__(
        self,
        stimulus: WindStimulusSpec,
        run_root: Path,
        *,
        runner: WindCommandRunner = run_gazebo_command,
        observer: Callable[..., AsyncIterator[RecordedWindObservation]] = observe_wind,
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        # Validate the command before creating resources.
        self._request = WindCommand.from_stimulus(stimulus)
        self._stimulus = stimulus
        self._root = Path(run_root).resolve()
        self._directory = self._root / "evidence" / "wind"
        self._runner = runner
        self._observer = observer
        self._clock = clock
        self._phase = "new"
        self._owns_directory = False
        self._wind_may_be_active = False
        self._cleanup_task: asyncio.Task[None] | None = None
        self._baseline: RecordedWindObservation | None = None
        self._receipt: WindCommandReceipt | None = None
        self._rejection: str | None = None

    @property
    def fault_type(self) -> Literal["wind"]:
        return "wind"

    def _require(self, phase: str) -> None:
        if self._phase != phase:
            raise FaultLifecycleError(
                f"wind controller must be {phase}; is {self._phase}"
            )

    def _save(self, name: str, record: dict) -> None:
        publish_text_exclusively(
            self._directory / name,
            json.dumps(record, indent=2, allow_nan=False) + "\n",
        )

    def _relative(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self._root).as_posix()

    async def prepare(self) -> None:
        self._require("new")
        self._phase = "preparing"
        parent = self._directory.parent.resolve()
        if not parent.is_dir() or not parent.is_relative_to(self._root):
            raise ValueError("run must contain its own evidence directory")
        self._directory.mkdir(exist_ok=False)
        self._owns_directory = True
        self._phase = "prepared"

    async def _publish(
        self, request: WindCommand, name: str, timeout_s: float
    ) -> WindCommandReceipt:
        record = {
            "schema_version": 1,
            "argv": request.arguments(),
            "timeout_s": timeout_s,
            "started_monotonic_ns": self._clock(),
            "finished_monotonic_ns": None,
            "output": None,
            "receipt": None,
            "error": None,
            "restoration_proven": False,
        }

        async def recording_runner(argv, *, timeout_s):
            output = await self._runner(argv, timeout_s=timeout_s)
            record["output"] = asdict(output)
            return output

        adapter = GazeboWindCommandAdapter(
            timeout_s=timeout_s,
            runner=recording_runner,
            clock=self._clock,
        )
        try:
            async with asyncio.timeout(timeout_s):
                receipt = await adapter.send(request)
            record["receipt"] = asdict(receipt)
        except BaseException as exc:
            record["finished_monotonic_ns"] = self._clock()
            record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            try:
                self._save(name, record)
            except Exception as write_error:
                exc.add_note(f"could not save wind command: {write_error}")
            raise

        record["finished_monotonic_ns"] = self._clock()
        self._save(name, record)
        return receipt

    async def activate(self) -> None:
        self._require("prepared")
        self._phase = "activating"

        # Call only after the flight owner has observed airborne.
        async with aclosing(self._observer(
            self._directory / "baseline",
            timeout_s=2.0,
            request_timeout_s=2.0,
            max_samples=1,
            runner=self._runner,
            clock=self._clock,
        )) as stream:
            self._baseline = await anext(stream)

        assert self._baseline is not None
        state = self._baseline.observation
        age = self._clock() - self._baseline.request_finished_monotonic_ns
        calm_limit = min(
            1e-6,
            float(self._stimulus.minimum_proven_speed_m_s) / 10,
        )
        if (
            not 0 <= age <= BASELINE_MAX_AGE_NS
            or state.paused
            or not state.link_wind_enabled
            or state.wind_speed_m_s > calm_limit
            or math.hypot(*state.wind_seed_world_m_s) > calm_limit
        ):
            self._rejection = "no fresh, calm, wind-enabled baseline"
        else:
            # Set before publishing: delivery can be unknown on failure.
            self._wind_may_be_active = True
            self._receipt = await self._publish(
                self._request,
                "command.json",
                min(2.0, float(self._stimulus.activation_timeout_s)),
            )
        self._phase = "requested"

    async def prove_activation(self) -> FaultActivationResult:
        self._require("requested")
        self._phase = "evaluating"
        assert self._baseline is not None
        samples: list[RecordedWindObservation] = []
        assessment = WindActivationAssessment(
            False,
            self._rejection or "activation window exhausted",
        )

        if self._receipt is not None:
            receipt = self._receipt
            deadline = (
                receipt.started_monotonic_ns
                + self._stimulus.activation_timeout_s * 1_000_000_000
            )
            remaining = (deadline - self._clock()) / 1_000_000_000
            if remaining > 0:
                assessment = WindActivationAssessment(
                    False, "no observations proved activation"
                )
                try:
                    async with aclosing(self._observer(
                        self._directory / "activation",
                        timeout_s=remaining,
                        request_timeout_s=min(2.0, remaining),
                        max_samples=1000,
                        runner=self._runner,
                        clock=self._clock,
                    )) as stream:
                        async for sample in stream:
                            samples.append(sample)
                            assessment = evaluate_wind_activation(
                                self._stimulus,
                                self._baseline,
                                samples,
                                command_started_monotonic_ns=(
                                    receipt.started_monotonic_ns
                                ),
                                command_finished_monotonic_ns=(
                                    receipt.finished_monotonic_ns
                                ),
                            )
                            if assessment.activated:
                                break
                except WindObservationTimeout:
                    assessment = WindActivationAssessment(
                        False, "observation budget exhausted before proof"
                    )

        assessed_at = self._clock()
        self._save("activation.json", {
            "schema_version": 1,
            "stimulus": self._stimulus.model_dump(mode="json"),
            "assessed_at_monotonic_ns": assessed_at,
            "activated": assessment.activated,
            "reason": assessment.reason,
            "command": (
                self._relative(self._directory / "command.json")
                if self._receipt else None
            ),
            "baseline": self._relative(self._baseline.artifact_path),
            "observations": [self._relative(s.artifact_path) for s in samples],
            "supporting_samples": [
                self._relative(s.artifact_path)
                for s in assessment.supporting_samples
            ],
        })
        evidence = EvidenceRef(
            source=EvidenceSource.HARNESS,
            clock_domain=ClockDomain.HOST_MONOTONIC,
            timestamp_us=assessed_at // 1000,
            signal="wind_activation.assessment",
            artifact_path=Path(self._relative(
                self._directory / "activation.json"
            )),
            description=assessment.reason,
        )
        self._phase = "evaluated"
        return FaultActivationResult(
            fault_type="wind",
            activated=assessment.activated,
            evidence=(evidence,),
        )

    async def _cleanup_once(self) -> None:
        self._phase = "cleaning"
        if self._owns_directory:
            if self._wind_may_be_active:
                await self._publish(
                    WindCommand.disabled(), "cleanup-command.json", 2.0
                )
                self._wind_may_be_active = False
            else:
                self._save("cleanup-command.json", {
                    "command_attempted": False,
                    "reason": "this controller never attempted wind publication",
                    "restoration_proven": False,
                })
        self._phase = "closed"

    async def cleanup(self) -> None:
        # One bounded attempt, shared by repeated cleanup calls.
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_once())
        cancellation = None
        while not self._cleanup_task.done():
            try:
                await asyncio.shield(self._cleanup_task)
            except asyncio.CancelledError as exc:
                cancellation = exc
            except Exception:
                break
        if cancellation is not None:
            try:
                self._cleanup_task.result()
            except BaseException as exc:
                cancellation.add_note(f"wind cleanup also failed: {exc}")
            raise cancellation
        self._cleanup_task.result()


@asynccontextmanager
async def managed_wind_controller(
    stimulus: WindStimulusSpec, run_root: Path, **options
) -> AsyncIterator[FaultLifecycle]:
    controller = GazeboWindController(stimulus, run_root, **options)
    lifecycle = FaultLifecycle(controller)
    try:
        await lifecycle.prepare()
        yield lifecycle
    except BaseException as exc:
        try:
            await lifecycle.cleanup()
        except BaseException as cleanup_error:
            exc.add_note(f"wind cleanup also failed: {cleanup_error}")
        raise
    else:
        await lifecycle.cleanup()