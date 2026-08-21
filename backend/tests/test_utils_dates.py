from datetime import date

import pytest

from src.utils.dates import next_weekday, prev_weekday


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 6, 5), date(2026, 6, 8)),  # Friday -> Monday
        (date(2026, 6, 6), date(2026, 6, 8)),  # Saturday -> Monday
        (date(2026, 6, 7), date(2026, 6, 8)),  # Sunday -> Monday
        (date(2026, 6, 10), date(2026, 6, 11)),  # Wednesday -> Thursday
    ],
)
def test_next_weekday(d: date, expected: date) -> None:
    assert next_weekday(d) == expected


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 6, 5), date(2026, 6, 4)),  # Friday -> Thursday
        (date(2026, 6, 8), date(2026, 6, 5)),  # Monday -> Friday
        (date(2026, 6, 10), date(2026, 6, 9)),  # Wednesday -> Tuesday
        (date(2026, 6, 6), date(2026, 6, 5)),  # Saturday -> Friday
        (date(2026, 6, 7), date(2026, 6, 5)),  # Sunday -> Friday
    ],
)
def test_prev_weekday(d: date, expected: date) -> None:
    assert prev_weekday(d) == expected
