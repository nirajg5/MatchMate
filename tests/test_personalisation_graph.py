from datetime import datetime
import pytest

from src.assistant.planning_repository import PlanningRepository
from src.assistant.personalisation_graph import _fallback_extract, run_planning_message


def _repo(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile(
        "Test Fan",
        {"favorite_teams": ["India"], "favorite_players": [],
         "favorite_tournaments": [], "preferred_match_types": [],
         "important_match_ids": []},
    )
    return repo, profile


def test_fallback_extract_requires_explicit_dates_for_plan():
    result = _fallback_extract("show matches from 2026-10-14 to 2026-10-20")
    assert result["intent"] == "generate_plan"
    assert result["start_date"] == "2026-10-14"
    assert result["end_date"] == "2026-10-20"


def test_fallback_extract_does_not_guess_natural_dates():
    result = _fallback_extract("show matches next week")
    assert result["intent"] == "generate_plan"
    assert "start_date" not in result


def test_graph_asks_for_dates_when_missing(tmp_path, monkeypatch):
    repo, profile = _repo(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(profile["profile_id"], "show matches", repository=repo)
    assert result["needs_clarification"] is True
    assert "date range" in result["response"].lower()


def test_graph_generates_and_saves_synthetic_plan(tmp_path, monkeypatch):
    repo, profile = _repo(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(
        profile["profile_id"],
        "show matches from 2026-10-14 to 2026-10-20",
        repository=repo,
    )
    assert result["plan"]
    assert all(item["is_simulated"] is True for item in result["plan"])
    assert len(repo.list_saved_plans(profile["profile_id"])) == 1


def test_graph_persists_user_and_assistant_messages(tmp_path, monkeypatch):
    repo, profile = _repo(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(
        profile["profile_id"], "show matches", repository=repo
    )
    messages = repo.list_messages(result["session_id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]


def test_graph_rejects_session_from_another_profile(tmp_path, monkeypatch):
    repo, profile1 = _repo(tmp_path)
    profile2 = repo.create_profile("Other")
    session = repo.create_session(profile2["profile_id"])
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(
        profile1["profile_id"], "hello", session_id=session["session_id"], repository=repo
    )
    assert "does not belong" in result["response"]


def test_graph_lists_commitments(tmp_path, monkeypatch):
    repo, profile = _repo(tmp_path)
    repo.add_commitment(
        profile["profile_id"], "Class", "2026-10-14T09:00",
        "2026-10-14T11:00", "Asia/Kolkata"
    )
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(
        profile["profile_id"], "show my commitments", repository=repo
    )
    assert "Class" in result["response"]


def test_graph_add_commitment_missing_fields_clarifies(tmp_path, monkeypatch):
    repo, profile = _repo(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = run_planning_message(
        profile["profile_id"], "add commitment", repository=repo
    )
    assert result["needs_clarification"] is True
