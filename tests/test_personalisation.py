"""Regression tests for the MatchPulse AI personalisation engine."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.assistant.match_schedule_service import (
    get_all_matches,
    get_match_by_id,
    get_matches_between_dates,
    get_playing_xi,
)
from src.assistant.personalisation_engine import (
    _calculate_match_score,
    _recommend_viewing,
    generate_personalised_plan,
)

TZ = ZoneInfo("Asia/Kolkata")


def empty_profile():
    return {
        "favorite_teams": [],
        "favorite_players": [],
        "favorite_tournaments": [],
        "preferred_match_types": [],
        "important_match_ids": [],
    }


def test_dataset_has_expected_synthetic_fixtures():
    matches = get_all_matches()
    assert len(matches) == 26
    assert all(match.get("is_simulated") is True for match in matches)


def test_match_ids_are_unique():
    ids = [str(match["match_id"]) for match in get_all_matches()]
    assert len(ids) == len(set(ids))


def test_every_fixture_has_22_playing_xi_rows():
    for match in get_all_matches():
        assert len(get_playing_xi(str(match["match_id"]))) == 22


def test_match_lookup_returns_existing_fixture():
    first = get_all_matches()[0]
    found = get_match_by_id(str(first["match_id"]))
    assert found is not None
    assert str(found["match_id"]) == str(first["match_id"])


def test_date_range_includes_boundaries():
    matches = get_all_matches()
    first_date = min(str(m["match_date"])[:10] for m in matches)
    result = get_matches_between_dates(first_date, first_date)
    assert result
    assert all(str(m["match_date"])[:10] == first_date for m in result)


def test_empty_date_range_returns_no_matches():
    assert get_matches_between_dates("2035-01-01", "2035-01-02") == []


def test_invalid_date_range_raises_value_error():
    with pytest.raises(ValueError):
        get_matches_between_dates("2026-10-20", "2026-10-14")


def test_match_score_stays_in_expected_range():
    match = get_all_matches()[0]
    score, reasons = _calculate_match_score(
        match, {**empty_profile(), "favorite_teams": [match["team_a"]]}
    )
    assert 0 <= score <= 100
    assert isinstance(reasons, list)


def test_plan_only_returns_matches_inside_selected_dates():
    first_date = min(str(m["match_date"])[:10] for m in get_all_matches())
    plan = generate_personalised_plan(
        empty_profile(), [], first_date, first_date, top_n=15,
        now=datetime(2026, 10, 1, tzinfo=TZ),
    )
    assert all(first_date <= str(item["match_date"])[:10] <= first_date for item in plan)


def test_plan_marks_every_result_as_simulated():
    matches = get_all_matches()
    first = min(str(m["match_date"])[:10] for m in matches)
    last = max(str(m["match_date"])[:10] for m in matches)
    plan = generate_personalised_plan(
        empty_profile(), [], first, last, top_n=30,
        now=datetime(2026, 10, 1, tzinfo=TZ),
    )
    assert all(item["is_simulated"] is True for item in plan)


def test_completed_match_recommends_catch_up():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    option, windows, status = _recommend_viewing(
        start, end, [], now=datetime(2026, 10, 15, 8, tzinfo=TZ)
    )
    assert (option, windows, status) == ("catch_up", [], "completed")


def test_currently_running_unblocked_match_is_live():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    option, windows, status = _recommend_viewing(
        start, end, [], now=datetime(2026, 10, 14, 18, tzinfo=TZ)
    )
    assert option == "live"
    assert status == "in_progress"
    assert int(windows[0]["duration_minutes"]) == 300


def test_future_unblocked_match_is_watch_full_not_live():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    option, _, status = _recommend_viewing(
        start, end, [], now=datetime(2026, 10, 14, 10, tzinfo=TZ)
    )
    assert option == "watch_full"
    assert status == "upcoming"


def test_short_free_window_is_not_partial_recommendation():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    commitments = [
        (datetime(2026, 10, 14, 15, 30, tzinfo=TZ),
         datetime(2026, 10, 14, 22, 30, tzinfo=TZ))
    ]
    option, windows, _ = _recommend_viewing(
        start, end, commitments, now=datetime(2026, 10, 14, 10, tzinfo=TZ)
    )
    assert option == "unavailable"
    assert windows


def test_sufficient_continuous_free_window_can_be_partial():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    commitments = [
        (datetime(2026, 10, 14, 17, tzinfo=TZ),
         datetime(2026, 10, 14, 21, tzinfo=TZ))
    ]
    option, windows, _ = _recommend_viewing(
        start, end, commitments, now=datetime(2026, 10, 14, 10, tzinfo=TZ)
    )
    assert option == "watch_partial"
    assert windows


def test_fully_blocked_match_is_unavailable():
    start = datetime(2026, 10, 14, 15, tzinfo=TZ)
    end = datetime(2026, 10, 14, 23, tzinfo=TZ)
    commitments = [(start, end)]
    option, _, _ = _recommend_viewing(
        start, end, commitments, now=datetime(2026, 10, 14, 10, tzinfo=TZ)
    )
    assert option == "unavailable"


def test_invalid_commitment_timezone_is_reported():
    with pytest.raises(ValueError, match="timezone"):
        generate_personalised_plan(
            empty_profile(),
            [{
                "title": "Test",
                "start_time_local": "2026-10-14T10:00",
                "end_time_local": "2026-10-14T11:00",
                "timezone": "Not/A_Timezone",
            }],
            "2026-10-14", "2026-10-14",
            now=datetime(2026, 10, 1, tzinfo=TZ),
        )


def test_missing_commitment_fields_are_reported():
    with pytest.raises(ValueError, match="missing"):
        generate_personalised_plan(
            empty_profile(), [{"title": "Broken"}],
            "2026-10-14", "2026-10-14",
            now=datetime(2026, 10, 1, tzinfo=TZ),
        )
