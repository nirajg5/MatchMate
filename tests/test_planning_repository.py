from datetime import datetime
import json

import pytest

from src.assistant.planning_repository import PlanningRepository


def test_profile_crud_and_preferences_roundtrip(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile("Niraj", {"favorite_teams": ["India"]})
    loaded = repo.get_profile(profile["profile_id"])
    assert loaded["display_name"] == "Niraj"
    assert loaded["preferences"]["favorite_teams"] == ["India"]

    updated = repo.update_profile(
        profile["profile_id"], preferences={"preferred_match_types": ["T20"]}
    )
    assert updated["preferences"]["preferred_match_types"] == ["T20"]


def test_commitment_add_list_delete(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile("Fan")
    item = repo.add_commitment(
        profile["profile_id"], "Class", "2026-10-14T10:00",
        "2026-10-14T12:00", "Asia/Kolkata",
    )
    assert len(repo.list_commitments(profile["profile_id"])) == 1
    assert repo.delete_commitment(item["commitment_id"], profile["profile_id"])
    assert repo.list_commitments(profile["profile_id"]) == []


def test_commitment_requires_profile_and_title(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    with pytest.raises(KeyError):
        repo.add_commitment("missing", "Class", "a", "b")
    profile = repo.create_profile()
    with pytest.raises(ValueError):
        repo.add_commitment(profile["profile_id"], " ", "a", "b")


def test_chat_messages_persist_in_order(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile()
    session = repo.create_session(profile["profile_id"])
    repo.add_message(session["session_id"], "user", "Show India matches")
    repo.add_message(session["session_id"], "assistant", "Here are simulated fixtures")
    messages = repo.list_messages(session["session_id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_message_rejects_invalid_role(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile()
    session = repo.create_session(profile["profile_id"])
    with pytest.raises(ValueError):
        repo.add_message(session["session_id"], "alien", "test")


def test_saved_plan_roundtrip_and_listing(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile()
    plan = [{"match_id": "SIM001", "is_simulated": True}]
    saved = repo.save_plan(profile["profile_id"], "2026-10-14", "2026-10-20", plan)
    assert repo.get_saved_plan(saved["plan_id"])["plan"] == plan
    assert len(repo.list_saved_plans(profile["profile_id"])) == 1


def test_saved_plan_rejects_invalid_date_range(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile()
    with pytest.raises(ValueError):
        repo.save_plan(profile["profile_id"], "2026-10-20", "2026-10-14", [])


def test_profile_deletion_cascades_to_related_records(tmp_path):
    repo = PlanningRepository(tmp_path / "planning.db")
    profile = repo.create_profile()
    pid = profile["profile_id"]
    repo.add_commitment(pid, "Work", "2026-10-14T09:00", "2026-10-14T17:00")
    session = repo.create_session(pid)
    repo.add_message(session["session_id"], "user", "hello")
    with repo._connect() as conn:
        conn.execute("DELETE FROM fan_profiles WHERE profile_id = ?", (pid,))
    assert repo.get_profile(pid) is None
    assert repo.list_commitments(pid) == []
    assert repo.get_session(session["session_id"]) is None
