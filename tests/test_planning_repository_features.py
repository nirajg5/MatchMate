from src.assistant.planning_repository import PlanningRepository

def test_multiple_sessions_and_titles(tmp_path):
    repo=PlanningRepository(tmp_path / "db.sqlite")
    profile=repo.create_profile("Fan", {})
    first=repo.create_session(profile["profile_id"], "First chat")
    second=repo.create_session(profile["profile_id"], "Second chat")
    assert {x["session_id"] for x in repo.list_sessions(profile["profile_id"])} == {first["session_id"],second["session_id"]}
    assert repo.update_session_title(first["session_id"],profile["profile_id"],"Work plan")
    assert repo.get_session(first["session_id"])["title"] == "Work plan"
    assert repo.delete_session(second["session_id"],profile["profile_id"])
    assert len(repo.list_sessions(profile["profile_id"])) == 1

def test_commitment_types_and_legacy_default(tmp_path):
    repo=PlanningRepository(tmp_path / "db.sqlite")
    profile=repo.create_profile("Fan", {})
    item=repo.add_commitment(profile["profile_id"],"Office","2026-10-14T09:00","2026-10-14T10:00",commitment_type="work")
    assert item["commitment_type"] == "work"
    old=repo.add_commitment(profile["profile_id"],"Other","2026-10-14T11:00","2026-10-14T12:00")
    assert old["commitment_type"] == "other"
