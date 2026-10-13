"""Deterministic match relevance and viewing-availability engine.

All fixtures are synthetic test data. This module does not verify real-world
cricket schedules or live match status.
"""
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.assistant.match_schedule_service import (
    get_matches_between_dates,
    get_playing_xi,
)

MIN_DISPLAY_WINDOW_MINUTES = 15
MIN_PARTIAL_WINDOW_MINUTES = 45
PARTIAL_DURATION_FRACTION = 0.25
DEFAULT_TIMEZONE = "Asia/Kolkata"


def _get_timezone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise ValueError(f"Unknown or invalid timezone: {timezone!r}") from exc


def _parse_datetime(value: str, timezone: str) -> datetime:
    """Parse a timestamp and return it in the requested timezone."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty datetime string is required.")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime value: {value!r}") from exc

    tz = _get_timezone(timezone)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _normalise(value: Any) -> str:
    return str(value).strip().casefold()


def _overlaps(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    """Return True if two half-open time intervals overlap."""
    return start_a < end_b and start_b < end_a


def _commitment_intervals(
    commitments: list[dict[str, Any]],
    timezone: str,
) -> list[tuple[datetime, datetime]]:
    """Validate commitments and normalize them to the match timezone."""
    target_tz = _get_timezone(timezone)
    intervals: list[tuple[datetime, datetime]] = []

    for index, item in enumerate(commitments):
        if not isinstance(item, dict):
            raise ValueError(f"Commitment #{index + 1} must be an object.")

        missing = [
            field for field in ("start_time_local", "end_time_local")
            if not item.get(field)
        ]
        if missing:
            raise ValueError(
                f"Commitment #{index + 1} is missing: {', '.join(missing)}."
            )

        item_timezone = item.get("timezone") or timezone
        start = _parse_datetime(
            item["start_time_local"], item_timezone
        ).astimezone(target_tz)
        end = _parse_datetime(
            item["end_time_local"], item_timezone
        ).astimezone(target_tz)

        if end <= start:
            title = item.get("title", f"Commitment #{index + 1}")
            raise ValueError(
                f"Invalid commitment interval for {title!r}: "
                "end time must be after start time."
            )
        intervals.append((start, end))

    return sorted(intervals, key=lambda interval: interval[0])


def _find_free_windows(
    match_start: datetime,
    match_end: datetime,
    commitments: list[tuple[datetime, datetime]],
) -> list[dict[str, str]]:
    """Return continuous free windows of at least 15 minutes."""
    if match_end <= match_start:
        return []

    cursor = match_start
    windows: list[dict[str, str]] = []

    for busy_start, busy_end in commitments:
        if busy_end <= cursor or busy_start >= match_end:
            continue

        free_end = min(busy_start, match_end)
        if free_end > cursor:
            minutes = int((free_end - cursor).total_seconds() // 60)
            if minutes >= MIN_DISPLAY_WINDOW_MINUTES:
                windows.append({
                    "start": cursor.isoformat(),
                    "end": free_end.isoformat(),
                    "duration_minutes": str(minutes),
                })

        cursor = max(cursor, busy_end)
        if cursor >= match_end:
            break

    if cursor < match_end:
        minutes = int((match_end - cursor).total_seconds() // 60)
        if minutes >= MIN_DISPLAY_WINDOW_MINUTES:
            windows.append({
                "start": cursor.isoformat(),
                "end": match_end.isoformat(),
                "duration_minutes": str(minutes),
            })

    return windows


def _get_relevant_players(match: dict[str, Any]) -> set[str]:
    """Collect names from the synthetic playing XI for this fixture."""
    return {
        _normalise(player["player_name"])
        for player in get_playing_xi(str(match["match_id"]))
        if player.get("player_name")
    }


def _calculate_match_score(
    match: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[int, list[str]]:
    """Calculate an explainable match relevance score out of 100."""
    score = 0
    reasons: list[str] = []

    favorite_teams = {
        _normalise(team) for team in profile.get("favorite_teams", [])
        if _normalise(team)
    }
    match_teams = {
        _normalise(match["team_a"]), _normalise(match["team_b"])
    }
    if favorite_teams & match_teams:
        score += 40
        reasons.append("Includes a favourite team")

    favorite_players = {
        _normalise(player) for player in profile.get("favorite_players", [])
        if _normalise(player)
    }
    if favorite_players and favorite_players & _get_relevant_players(match):
        score += 25
        reasons.append("Includes a favourite player in the simulated XI")

    favorite_tournaments = {
        _normalise(item) for item in profile.get("favorite_tournaments", [])
        if _normalise(item)
    }
    if _normalise(match["tournament"]) in favorite_tournaments:
        score += 15
        reasons.append("Matches a preferred tournament")

    preferred_types = {
        _normalise(item) for item in profile.get("preferred_match_types", [])
        if _normalise(item)
    }
    if _normalise(match["match_type"]) in preferred_types:
        score += 10
        reasons.append("Matches a preferred format")

    important_ids = {str(item) for item in profile.get("important_match_ids", [])}
    if str(match["match_id"]) in important_ids:
        score += 10
        reasons.append("Marked as important by the fan")

    if not reasons:
        reasons.append("No explicit preference matched")

    return min(score, 100), reasons


def _meaningful_partial_window(
    windows: list[dict[str, str]],
    remaining_duration_minutes: float,
) -> bool:
    """Require one continuous window large enough to be useful."""
    if not windows:
        return False
    threshold = max(
        MIN_PARTIAL_WINDOW_MINUTES,
        remaining_duration_minutes * PARTIAL_DURATION_FRACTION,
    )
    return max(int(window["duration_minutes"]) for window in windows) >= threshold


def _recommend_viewing(
    match_start: datetime,
    match_end: datetime,
    commitments: list[tuple[datetime, datetime]],
    now: datetime | None = None,
) -> tuple[str, list[dict[str, str]], str]:
    """Return (viewing_option, free_windows, match_status).

    viewing_option values: live, watch_full, watch_partial, catch_up, unavailable.
    match_status values: upcoming, in_progress, completed.
    """
    if match_end <= match_start:
        raise ValueError("Match end time must be after its start time.")

    current = now or datetime.now(match_start.tzinfo)
    if current.tzinfo is None:
        current = current.replace(tzinfo=match_start.tzinfo)
    else:
        current = current.astimezone(match_start.tzinfo)

    if match_end <= current:
        return "catch_up", [], "completed"

    match_status = "in_progress" if match_start <= current < match_end else "upcoming"
    effective_start = max(match_start, current)

    future_commitments = [
        (max(start, effective_start), end)
        for start, end in commitments
        if end > effective_start and start < match_end
    ]
    has_conflict = any(
        _overlaps(effective_start, match_end, start, end)
        for start, end in future_commitments
    )

    if not has_conflict:
        duration = int((match_end - effective_start).total_seconds() // 60)
        windows = [{
            "start": effective_start.isoformat(),
            "end": match_end.isoformat(),
            "duration_minutes": str(duration),
        }]
        return ("live" if match_status == "in_progress" else "watch_full",
                windows, match_status)

    windows = _find_free_windows(
        effective_start, match_end, future_commitments
    )
    remaining_minutes = (match_end - effective_start).total_seconds() / 60

    if _meaningful_partial_window(windows, remaining_minutes):
        return "watch_partial", windows, match_status

    return "unavailable", windows, match_status


def generate_personalised_plan(
    profile: dict[str, Any],
    commitments: list[dict[str, Any]],
    start_date: str | date,
    end_date: str | date,
    top_n: int = 10,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Generate a personalised plan from the local synthetic fixture dataset.

    The optional ``now`` parameter makes time-dependent behaviour testable.
    It must be timezone-aware or will be interpreted in each fixture timezone.
    """
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError("top_n must be a positive integer.")
    if not isinstance(profile, dict):
        raise ValueError("profile must be a dictionary.")
    if not isinstance(commitments, list):
        raise ValueError("commitments must be a list.")

    matches = get_matches_between_dates(start_date, end_date)
    results: list[dict[str, Any]] = []

    for match in matches:
        timezone = match.get("timezone", DEFAULT_TIMEZONE)
        _get_timezone(timezone)

        if match.get("is_simulated") is not True:
            raise ValueError(
                "This prototype expects explicitly marked synthetic fixtures."
            )

        match_start = _parse_datetime(match["start_time_local"], timezone)
        match_end = _parse_datetime(match["estimated_end_time_local"], timezone)
        if match_end <= match_start:
            continue

        current = now
        if current is not None:
            if current.tzinfo is None:
                current = current.replace(tzinfo=_get_timezone(timezone))
            else:
                current = current.astimezone(_get_timezone(timezone))

        score, reasons = _calculate_match_score(match, profile)
        busy_intervals = _commitment_intervals(commitments, timezone)
        viewing_option, free_windows, match_status = _recommend_viewing(
            match_start, match_end, busy_intervals, current
        )

        results.append({
            "match_id": match["match_id"],
            "match_name": match["match_name"],
            "match_date": match["match_date"],
            "start_time": match["start_time_local"],
            "estimated_end_time": match["estimated_end_time_local"],
            "timezone": timezone,
            "match_type": match["match_type"],
            "tournament": match["tournament"],
            "venue": match["venue"],
            "relevance_score": score,
            "recommendation_reasons": reasons,
            "viewing_option": viewing_option,
            "match_status": match_status,
            "available_viewing_windows": free_windows,
            "data_source": match["data_source"],
            "is_simulated": True,
            "playing_xi_status": match["playing_xi_status"],
        })

    results.sort(key=lambda item: (
        -item["relevance_score"],
        item["start_time"],
        item["match_id"],
    ))
    return results[:top_n]
