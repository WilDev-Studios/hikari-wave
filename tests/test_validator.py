from hikariwave.config import (
    validate_bitrate,
    validate_channels,
    validate_volume,
)

import pytest

@pytest.mark.parametrize(
    "input_value,expected", [
        ("6k", "6k"),
        ("96k", "96k"),
        ("510k", "510k"),
        (" 128k ", "128k"),
    ],
)
def test_bitrates_valid(input_value: str, expected: str) -> None:
    assert validate_bitrate(input_value) == expected

@pytest.mark.parametrize(
    "input_value",
    ["5k", "511k", "abc", "100", 100, None],
)
def test_bitrates_invalid(input_value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        validate_bitrate(input_value)


@pytest.mark.parametrize(
    "input_value,expected",
    [(1, 1), (2, 2)],
)
def test_valid_channels(input_value: int, expected: int):
    assert validate_channels(input_value) == expected

@pytest.mark.parametrize(
    "input_value",
    [0, 3, -1, "2", None],
)
def test_invalid_channels(input_value: object):
    with pytest.raises((ValueError, TypeError)):
        validate_channels(input_value)


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (1.0, 1.0),
        (0.5, 0.5),
        (10, 10.0),
        ("+3dB", "+3dB"),
        ("-2.5dB", "-2.5dB"),
        ("0dB", "0dB"),
    ],
)
def test_valid_volumes(input_value: float | int | str, expected: float | str):
    assert validate_volume(input_value) == expected

@pytest.mark.parametrize(
    "input_value",
    [
        -1.0, -5,
        "3", "dB",
        "3db", "+dB",
        None, [], {},
    ],
)
def test_invalid_volumes(input_value: object):
    with pytest.raises((ValueError, TypeError)):
        validate_volume(input_value)