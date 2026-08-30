# tests for PX4 ULog land-detection analysis

from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_ci.analysis import (
    ULogAnalysisError,
    analyze_land_detection,
)


def make_ulog_file(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "flight.ulg"
    path.write_bytes(b"fake-ulog")
    return path


def make_dataset(
    *,
    timestamps=None,
    landed=None,
    multi_id: int = 0,
):
    data = {}

    if timestamps is not None:
        data["timestamp"] = timestamps

    if landed is not None:
        data["landed"] = landed

    return SimpleNamespace(
        name="vehicle_land_detected",
        multi_id=multi_id,
        data=data,
    )


def make_factory(*datasets):
    def factory(
        log_file_name: str,
        message_name_filter_list=None,
    ):
        assert Path(log_file_name).is_file()
        assert message_name_filter_list == [
            "vehicle_land_detected"
        ]

        return SimpleNamespace(
            data_list=list(datasets)
        )

    return factory


def test_takeoff_and_landing_are_summarized(
    tmp_path: Path,
) -> None:
    dataset = make_dataset(
        timestamps=[
            10,
            20,
            30,
            40,
            50,
            60,
        ],
        landed=[
            1,
            1,
            0,
            0,
            1,
            1,
        ],
    )

    summary = analyze_land_detection(
        make_ulog_file(tmp_path),
        ulog_factory=make_factory(dataset),
    )

    assert summary.sample_count == 6
    assert summary.first_timestamp_us == 10
    assert summary.last_timestamp_us == 60
    assert summary.initial_landed is True
    assert summary.airborne_observed is True
    assert (
        summary.first_airborne_timestamp_us
        == 30
    )
    assert summary.final_landed is True
    assert (
        summary.landing_transition_observed
        is True
    )
    assert summary.landing_timestamp_us == 50


def test_grounded_log_does_not_invent_transitions(
    tmp_path: Path,
) -> None:
    dataset = make_dataset(
        timestamps=[10, 20, 30],
        landed=[1, 1, 1],
    )

    summary = analyze_land_detection(
        make_ulog_file(tmp_path),
        ulog_factory=make_factory(dataset),
    )

    assert summary.initial_landed is True
    assert summary.airborne_observed is False
    assert (
        summary.first_airborne_timestamp_us
        is None
    )
    assert summary.final_landed is True
    assert (
        summary.landing_transition_observed
        is False
    )
    assert summary.landing_timestamp_us is None


def test_missing_ulog_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ULogAnalysisError,
        match="does not exist",
    ):
        analyze_land_detection(
            tmp_path / "missing.ulg"
        )


def test_missing_dataset_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ULogAnalysisError,
        match="found 0",
    ):
        analyze_land_detection(
            make_ulog_file(tmp_path),
            ulog_factory=make_factory(),
        )


def test_multiple_datasets_are_rejected(
    tmp_path: Path,
) -> None:
    first = make_dataset(
        timestamps=[10],
        landed=[1],
    )
    second = make_dataset(
        timestamps=[10],
        landed=[1],
    )

    with pytest.raises(
        ULogAnalysisError,
        match="found 2",
    ):
        analyze_land_detection(
            make_ulog_file(tmp_path),
            ulog_factory=make_factory(
                first,
                second,
            ),
        )


@pytest.mark.parametrize(
    ("dataset", "message"),
    [
        (
            make_dataset(
                landed=[1],
            ),
            "missing required field 'timestamp'",
        ),
        (
            make_dataset(
                timestamps=[10, 20],
                landed=[1],
            ),
            "different lengths",
        ),
        (
            make_dataset(
                timestamps=[10],
                landed=[2],
            ),
            "only 0 or 1",
        ),
        (
            make_dataset(
                timestamps=[20, 10],
                landed=[1, 1],
            ),
            "must be ordered",
        ),
    ],
)
def test_malformed_dataset_is_rejected(
    tmp_path: Path,
    dataset,
    message: str,
) -> None:
    with pytest.raises(
        ULogAnalysisError,
        match=message,
    ):
        analyze_land_detection(
            make_ulog_file(tmp_path),
            ulog_factory=make_factory(dataset),
        )