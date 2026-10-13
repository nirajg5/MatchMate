from src.assistant.personalisation_graph import extract_intent


def test_greeting_variants_do_not_fall_through_to_help():
    for message in ("hi", "hii", "hello", "hey", "good morning"):
        assert extract_intent(message)["intent"] == "greeting"


def test_match_request_still_routes_to_plan():
    result = extract_intent("Show matches from 2026-10-14 to 2026-10-20")
    assert result["intent"] == "generate_plan"
    assert result["start_date"] == "2026-10-14"
    assert result["end_date"] == "2026-10-20"


def test_saved_plan_is_not_new_plan():
    assert extract_intent("Show my saved plan")["intent"] == "show_saved_plan"
