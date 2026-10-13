import json
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "personalised_planning"


def _load_json(filename: str) -> list[dict[str, Any]]:
    """Load a JSON dataset and validate its top-level structure."""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}. Check the personalised_planning data directory."
        )
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{filename} must contain a JSON list.")
    return data


def get_all_matches() -> list[dict[str, Any]]:
    """Return all available synthetic match fixtures."""
    return _load_json("matches.json")


def get_matches_between_dates(start_date: str | date, end_date: str | date) -> list[dict[str, Any]]:
    """Return matches scheduled within an inclusive date range."""
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    if start > end:
        raise ValueError("start_date must not be after end_date.")
    matches = [m for m in get_all_matches() if start <= date.fromisoformat(m["match_date"]) <= end]
    return sorted(matches, key=lambda m: (m.get("start_time_local", ""), m.get("match_id", "")))


def get_matches_for_date(match_date: str | date) -> list[dict[str, Any]]:
    return get_matches_between_dates(match_date, match_date)


def get_upcoming_matches(from_date: str | date | None = None) -> list[dict[str, Any]]:
    selected_date = from_date or date.today()
    return get_matches_between_dates(selected_date, date.max)


def get_match_by_id(match_id: str) -> dict[str, Any] | None:
    return next((m for m in get_all_matches() if m.get("match_id") == match_id), None)


def get_playing_xi(match_id: str, team_code: str | None = None) -> list[dict[str, Any]]:
    players = _load_json("playing_xi.json")
    return [p for p in players if p.get("match_id") == match_id and (team_code is None or str(p.get("team_code", "")).upper() == team_code.upper())]


def get_team_squad(team_code: str) -> list[dict[str, Any]]:
    players = _load_json("team_squads.json")
    return [p for p in players if str(p.get("team_code", "")).upper() == team_code.upper()]


if __name__ == "__main__":
    matches = get_all_matches()
    print(f"Total simulated fixtures: {len(matches)}")
    if matches:
        print(json.dumps(matches[0], indent=2))
