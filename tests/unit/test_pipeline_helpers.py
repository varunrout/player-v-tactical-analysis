import pytest

from src.ingestion.pipeline import (
    _coerce_clock_to_minute,
    _determine_primary_position,
    _extract_lineup_minutes,
    _is_lineup_starter,
)


def test_coerce_clock_to_minute_parses_standard_clock():
    minute = _coerce_clock_to_minute("68:21")
    assert minute == pytest.approx(68 + 21 / 60, rel=1e-3)


def test_coerce_clock_to_minute_handles_invalid_input():
    assert _coerce_clock_to_minute(None) is None
    assert _coerce_clock_to_minute("invalid") is None


def test_extract_lineup_minutes_uses_earliest_and_latest_segments():
    positions = [
        {"from": "00:00", "to": "45:00"},
        {"from": "60:00", "to": "90:00"},
    ]
    start, end = _extract_lineup_minutes(positions)
    assert start == pytest.approx(0)
    assert end == pytest.approx(90)


def test_is_lineup_starter_detects_starting_xi():
    starter_positions = [{"start_reason": "Starting XI"}]
    sub_positions = [{"start_reason": "Substitution - On (Tactical)"}]
    assert _is_lineup_starter(starter_positions) is True
    assert _is_lineup_starter(sub_positions) is False


def test_determine_primary_position_prefers_first_entry():
    positions = [
        {"position": "Center Back"},
        {"position": "Right Back"},
    ]
    assert _determine_primary_position(positions) == "Center Back"
    assert _determine_primary_position([]) is None
