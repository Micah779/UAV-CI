# typed post-flight analysis of PX4 ULogs

from collections.abc import (
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pyulog import ULog


LAND_DETECTION_TOPIC = (
    "vehicle_land_detected"
)


class ULogDataset(Protocol):
    name: str
    multi_id: int
    data: Mapping[str, Sequence[object]]


class ULogDocument(Protocol):
    data_list: list[ULogDataset]


class ULogFactory(Protocol):
    def __call__(
        self,
        log_file_name: str,
        message_name_filter_list: (
            list[str] | None
        ) = None,
    ) -> ULogDocument:
        ...


class ULogAnalysisError(RuntimeError):
    # ULog evidence could not be interpreted
    pass


@dataclass(frozen=True, slots=True)
class LandDetectionSummary:
    # validated vehicle_land_detected evidence

    topic: str
    instance: int
    sample_count: int

    first_timestamp_us: int
    last_timestamp_us: int

    initial_landed: bool
    airborne_observed: bool
    first_airborne_timestamp_us: int | None

    final_landed: bool
    landing_transition_observed: bool
    landing_timestamp_us: int | None


def _load_required_series(
    dataset: ULogDataset,
    field_name: str,
) -> list[object]:
    try:
        values = list(
            dataset.data[field_name]
        )
    except KeyError as exc:
        raise ULogAnalysisError(
            f"{LAND_DETECTION_TOPIC} is missing "
            f"required field {field_name!r}"
        ) from exc
    except TypeError as exc:
        raise ULogAnalysisError(
            f"{LAND_DETECTION_TOPIC} field "
            f"{field_name!r} is not a series"
        ) from exc

    return values


def _normalize_timestamps(
    values: Sequence[object],
) -> tuple[int, ...]:
    try:
        timestamps = tuple(
            int(value)
            for value in values
        )
    except (TypeError, ValueError) as exc:
        raise ULogAnalysisError(
            "land-detection timestamps must "
            "be integers"
        ) from exc

    if any(
        timestamp < 0
        for timestamp in timestamps
    ):
        raise ULogAnalysisError(
            "land-detection timestamps cannot "
            "be negative"
        )

    if any(
        current < previous
        for previous, current in zip(
            timestamps,
            timestamps[1:],
        )
    ):
        raise ULogAnalysisError(
            "land-detection timestamps must "
            "be ordered"
        )

    return timestamps


def _normalize_landed_values(
    values: Sequence[object],
) -> tuple[bool, ...]:
    normalized: list[bool] = []

    for value in values:
        try:
            numeric_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ULogAnalysisError(
                "landed values must be boolean"
            ) from exc

        if (
            numeric_value not in {0, 1}
            or value != numeric_value
        ):
            raise ULogAnalysisError(
                "landed values must contain "
                "only 0 or 1"
            )

        normalized.append(
            bool(numeric_value)
        )

    return tuple(normalized)


def analyze_land_detection(
    ulog_path: str | Path,
    *,
    ulog_factory: ULogFactory = ULog,
) -> LandDetectionSummary:
    # summarize takeoff and landing evidence

    resolved_path = Path(
        ulog_path
    ).resolve()

    if not resolved_path.is_file():
        raise ULogAnalysisError(
            f"ULog does not exist: {resolved_path}"
        )

    if resolved_path.stat().st_size == 0:
        raise ULogAnalysisError(
            "ULog is empty"
        )

    try:
        document = ulog_factory(
            str(resolved_path),
            message_name_filter_list=[
                LAND_DETECTION_TOPIC
            ],
        )
    except Exception as exc:
        raise ULogAnalysisError(
            f"pyulog could not parse the ULog: {exc}"
        ) from exc

    datasets = [
        dataset
        for dataset in document.data_list
        if dataset.name == LAND_DETECTION_TOPIC
    ]

    if len(datasets) != 1:
        raise ULogAnalysisError(
            "expected exactly one "
            f"{LAND_DETECTION_TOPIC} dataset, "
            f"found {len(datasets)}"
        )

    dataset = datasets[0]

    if dataset.multi_id != 0:
        raise ULogAnalysisError(
            "vehicle_land_detected must use "
            "instance 0"
        )

    timestamp_values = _load_required_series(
        dataset,
        "timestamp",
    )
    landed_values = _load_required_series(
        dataset,
        "landed",
    )

    if not timestamp_values:
        raise ULogAnalysisError(
            "vehicle_land_detected contains "
            "no samples"
        )

    if len(timestamp_values) != len(
        landed_values
    ):
        raise ULogAnalysisError(
            "timestamp and landed series have "
            "different lengths"
        )

    timestamps = _normalize_timestamps(
        timestamp_values
    )
    landed = _normalize_landed_values(
        landed_values
    )

    airborne_indices = [
        index
        for index, value in enumerate(landed)
        if not value
    ]

    first_airborne_index = (
        airborne_indices[0]
        if airborne_indices
        else None
    )

    landing_transition_indices = [
        index
        for index in range(1, len(landed))
        if (
            not landed[index - 1]
            and landed[index]
        )
    ]

    final_landing_index = (
        landing_transition_indices[-1]
        if landing_transition_indices
        else None
    )

    return LandDetectionSummary(
        topic=LAND_DETECTION_TOPIC,
        instance=dataset.multi_id,
        sample_count=len(timestamps),
        first_timestamp_us=timestamps[0],
        last_timestamp_us=timestamps[-1],
        initial_landed=landed[0],
        airborne_observed=(
            first_airborne_index is not None
        ),
        first_airborne_timestamp_us=(
            timestamps[first_airborne_index]
            if first_airborne_index is not None
            else None
        ),
        final_landed=landed[-1],
        landing_transition_observed=(
            final_landing_index is not None
        ),
        landing_timestamp_us=(
            timestamps[final_landing_index]
            if final_landing_index is not None
            else None
        ),
    )