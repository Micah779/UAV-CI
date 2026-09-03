'''
Purpose: connect the existing command runner, decoder, and evidence writer.
Each saved JSON record contains:
- The command and host-monotonic timing.
- Returned stdout and stderr.
- Decoded simulator observations, when available.
- Error information if the attempt failed.
The observer uses an async generator: the caller receives samples one at a time and can stop early. It has both a total observation budget and a per-request timeout. Cancellation is allowed to propagate after cleanup.
'''

# bounded, read-only Gazebo state collection with retained evidence.

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from time import monotonic_ns

from uav_ci.faults.wind_command import (
    WindCommandRunner,
    run_gazebo_command,
)
from uav_ci.faults.wind_state import (
    WindStateObservation,
    decode_wind_state,
)
from uav_ci.runtime.files import publish_text_exclusively
from uav_ci.faults.gazebo_diagnostics import has_unrecognized_stderr

class WindObservationError(RuntimeError):
    pass


class WindObservationTimeout(WindObservationError):
    pass


@dataclass(frozen=True, slots=True)
class RecordedWindObservation:
    observation: WindStateObservation
    artifact_path: Path
    request_started_monotonic_ns: int
    request_finished_monotonic_ns: int


def _positive(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be finite and positive"
        )


def _save(path: Path, record: dict) -> None:
    publish_text_exclusively(
        path,
        json.dumps(
            record,
            indent=2,
            allow_nan=False,
        ) + "\n",
    )


async def observe_wind(
    output_directory: Path,
    *,
    timeout_s: float = 8.0,
    request_timeout_s: float = 2.0,
    poll_interval_s: float = 0.25,
    max_samples: int = 20,
    runner: WindCommandRunner = run_gazebo_command,
    clock: Callable[[], int] = monotonic_ns,
) -> AsyncIterator[RecordedWindObservation]:
    # yield recorded samples; caller owns simulator launch and shutdown.
    _positive(timeout_s, "timeout_s")
    _positive(request_timeout_s, "request_timeout_s")
    _positive(poll_interval_s, "poll_interval_s")

    if (
        type(max_samples) is not int
        or not 1 <= max_samples <= 1000
    ):
        raise ValueError(
            "max_samples must be an integer from 1 to 1000"
        )

    # Each observation session needs its own unused directory.
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(exist_ok=False)

    deadline = clock() + int(timeout_s * 1_000_000_000)

    for index in range(1, max_samples + 1):
        started = clock()
        remaining = (
            deadline - started
        ) / 1_000_000_000

        if remaining <= 0:
            raise WindObservationTimeout(
                "observation budget exhausted; "
                f"evidence: {output_directory}"
            )

        request_budget = min(
            request_timeout_s,
            remaining,
        )

        # Gazebo service timeout uses integer milliseconds.
        service_ms = max(
            1,
            min(5000, int(request_budget * 1000)),
        )

        argv = (
            "gz",
            "service",
            "-s",
            "/world/default/state",
            "--reqtype",
            "gz.msgs.Empty",
            "--reptype",
            "gz.msgs.SerializedStepMap",
            "--timeout",
            str(service_ms),
            "--req",
            "",
        )

        path = (
            output_directory
            / f"sample-{index:06d}.json"
        )

        record = {
            "schema_version": 1,
            "sample_index": index,
            "argv": argv,
            "request_timeout_s": request_budget,
            "request_started_monotonic_ns": started,
            "request_finished_monotonic_ns": None,
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "observation": None,
            "error": None,
        }

        try:
            # Also bound injected runners that neglect their timeout.
            async with asyncio.timeout(request_budget):
                output = await runner(
                    argv,
                    timeout_s=request_budget,
                )

            finished = clock()

            record.update(
                request_finished_monotonic_ns=finished,
                returncode=output.returncode,
                stdout=output.stdout,
                stderr=output.stderr,
            )

            if (
                finished >= deadline
                or finished - started > request_budget * 1e9
            ):
                raise TimeoutError(
                    "state response arrived after its deadline"
                )

            if output.returncode != 0:
                raise WindObservationError(
                    f"state command exited {output.returncode}"
                )

            if has_unrecognized_stderr(output.stderr):
                raise WindObservationError(
                    "unrecognized state-command stderr"
                )

            observation = decode_wind_state(
                output.stdout
            )

            record["observation"] = asdict(
                observation
            )

        except asyncio.CancelledError as exc:
            record["request_finished_monotonic_ns"] = clock()
            record["error"] = {
                "type": "CancelledError",
                "message": "observation cancelled",
            }

            try:
                _save(path, record)
            except OSError as write_error:
                exc.add_note(
                    "could not record cancellation: "
                    f"{write_error}"
                )

            raise

        except Exception as exc:
            if record["request_finished_monotonic_ns"] is None:
                record["request_finished_monotonic_ns"] = clock()

            record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

            _save(path, record)

            error_type = (
                WindObservationTimeout
                if isinstance(exc, TimeoutError)
                else WindObservationError
            )

            raise error_type(
                "state observation failed; "
                f"evidence: {path}"
            ) from exc

        # Never deliver a sample whose evidence was not saved.
        _save(path, record)

        yield RecordedWindObservation(
            observation=observation,
            artifact_path=path,
            request_started_monotonic_ns=started,
            request_finished_monotonic_ns=finished,
        )

        if index < max_samples:
            remaining = (
                deadline - clock()
            ) / 1_000_000_000

            if remaining > 0:
                await asyncio.sleep(
                    min(poll_interval_s, remaining)
                )