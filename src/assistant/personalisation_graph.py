"""LangGraph orchestration for MatchPulse AI Personalised Planning.

The repository is the source of truth for stored preferences, commitments,
sessions, and saved plans. The deterministic engine ranks fixtures and
calculates viewing options. Groq is used only to interpret user messages.
All fixtures used by this prototype are synthetic.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, TypedDict

from src.assistant.personalisation_engine import generate_personalised_plan
from src.assistant.planning_repository import PlanningRepository

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # provide a clear install hint at graph construction
    END = START = StateGraph = None  # type: ignore[assignment]
    _LANGGRAPH_IMPORT_ERROR = exc
else:
    _LANGGRAPH_IMPORT_ERROR = None


PREFERENCE_KEYS = {
    "favorite_teams",
    "favorite_players",
    "favorite_tournaments",
    "preferred_match_types",
    "important_match_ids",
}


class PlanningState(TypedDict, total=False):
    profile_id: str
    session_id: str
    message: str
    profile: dict[str, Any]
    commitments: list[dict[str, Any]]
    extracted: dict[str, Any]
    intent: str
    response: str
    plan: list[dict[str, Any]]
    start_date: str
    end_date: str
    needs_clarification: bool
    error: str


def _fallback_extract(message: str) -> dict[str, Any]:
    """Offline fallback for basic intents; prioritise specific intents first."""
    text = message.strip()
    lowered = text.casefold()
    intent = "help"

    # IMPORTANT: check specific phrases before the broad word "plan".
    # Otherwise "Show my saved plan" is incorrectly classified as generate_plan.
    if any(phrase in lowered for phrase in (
        "show my saved plan", "saved plan", "previous plan", "last plan",
        "list saved plans", "show saved plans",
    )):
        intent = "show_saved_plan"
    elif any(phrase in lowered for phrase in (
        "my commitments", "show commitments", "list commitments",
    )):
        intent = "list_commitments"
    elif any(phrase in lowered for phrase in (
        "delete commitment", "remove commitment", "cancel commitment",
    )):
        intent = "delete_commitment"
    elif any(phrase in lowered for phrase in (
        "add commitment", "add event", "schedule class", "schedule work",
        "add a meeting", "add study", "add workout", "add appointment",
        "add travel", "add family", "add chore", "add sleep", "add meal",
    )):
        intent = "add_commitment"
    elif any(phrase in lowered for phrase in (
        "update preference", "favorite team", "favourite team", "i like",
        "favourite player", "favorite player", "prefer t20", "prefer odi",
    )):
        intent = "update_preferences"
    elif any(phrase in lowered for phrase in (
        "plan", "recommend", "matches", "match schedule", "what games",
        "viewing schedule", "viewing plan",
    )):
        intent = "generate_plan"

    # Explicit ISO dates are also accepted as a follow-up answer to the
    # chatbot's date questions, even when the user sends dates without a verb.
    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if intent == "help" and dates:
        intent = "generate_plan"

    result: dict[str, Any] = {"intent": intent}
    if len(dates) >= 2:
        result["start_date"], result["end_date"] = dates[0], dates[1]
    elif len(dates) == 1:
        result["start_date"] = result["end_date"] = dates[0]

    if intent == "update_preferences":
        result["preferences"] = {}
    return result


def _extract_preferences_deterministically(message: str) -> dict[str, list[str]]:
    """Parse common preference statements without depending on an LLM response."""
    text = message.strip()
    lower = text.casefold()
    patterns = {
        "favorite_teams": r"(?:favourite|favorite)\s+teams?\s*[:=]\s*([^\n,;]+)|(?:my\s+)?(?:favourite|favorite)\s+team\s+is\s+([^\n.!?]+)",
        "favorite_players": r"(?:favourite|favorite)\s+players?\s*[:=]\s*([^\n;]+)|(?:my\s+)?(?:favourite|favorite)\s+players?\s+are\s+([^\n.!?]+)",
        "favorite_tournaments": r"(?:favourite|favorite)\s+tournaments?\s*[:=]\s*([^\n;]+)|(?:my\s+)?(?:favourite|favorite)\s+tournaments?\s+are\s+([^\n.!?]+)",
        "preferred_match_types": r"(?:preferred\s+match\s+formats?|match\s+formats?|formats?)\s*[:=]\s*([^\n;]+)|(?:i\s+)?prefer\s+(t20|odi|test|t10)(?:\s+matches?)?",
    }
    found: dict[str, list[str]] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = next((group for group in match.groups() if group), "")
        values = [v.strip(" .!\t-*#") for v in re.split(r",|/|\band\b", value, flags=re.IGNORECASE) if v.strip(" .!\t-*#")]
        if values:
            found[key] = list(dict.fromkeys(values))
    # Handle concise forms such as "India is my favourite team".
    if not found.get("favorite_teams"):
        m = re.search(r"\b([A-Za-z][A-Za-z .'-]{1,30})\s+is\s+my\s+(?:favourite|favorite)\s+team\b", text, re.I)
        if m:
            found["favorite_teams"] = [m.group(1).strip()]
    if found and any(term in lower for term in ("preference", "favourite", "favorite", "prefer", "match format", "tournament")):
        return found
    return {}


def extract_intent(message: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract structured action data with Groq, falling back safely when unavailable."""
    # Greetings are conversational turns, not unknown planning commands.
    lowered = message.casefold().strip()
    normalised = re.sub(r"[^\w\s']", "", lowered).strip()
    if re.fullmatch(
        r"(?:hi+|hello+|hey+|hiya|howdy|good morning|good afternoon|good evening)(?: there)?",
        normalised,
    ):
        return {"intent": "greeting"}
    # Parse explicit preference updates deterministically first. This prevents
    # the LLM from acknowledging a preference without actually saving it.
    deterministic_preferences = _extract_preferences_deterministically(message)
    if deterministic_preferences:
        return {"intent": "update_preferences", "preferences": deterministic_preferences}

    # Deterministic guard for this common action: do not let a broad LLM
    # classification turn "Show my saved plan" into a new plan request.
    lowered = message.casefold().strip()
    if any(phrase in lowered for phrase in (
        "show my saved plan", "saved plan", "previous plan", "last plan",
        "list saved plans", "show saved plans",
    )):
        return {"intent": "show_saved_plan"}
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return _fallback_extract(message)

        from langchain_groq import ChatGroq

        if not api_key:
            return _fallback_extract(message)

        llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0,
            api_key=api_key,
            timeout=20,
            max_retries=1,
        )
        today = date.today().isoformat()
        prompt = f"""
You extract intent and fields for a local cricket fan planning assistant.
Today is {today}. Interpret relative dates using today. Return ONLY one JSON object.
Never invent match data. Fixtures in this prototype are synthetic.
Allowed intent values:
generate_plan, update_preferences, add_commitment, list_commitments,
delete_commitment, show_saved_plan, help.
Schema:
{{
 "intent": "one allowed value",
 "start_date": "YYYY-MM-DD or null",
 "end_date": "YYYY-MM-DD or null",
 "preferences": {{
   "favorite_teams": ["..."],
   "favorite_players": ["..."],
   "favorite_tournaments": ["..."],
   "preferred_match_types": ["..."],
   "important_match_ids": ["..."]
 }},
 "commitment": {{
   "title": "string or null",
   "commitment_type": "work|meeting|class|study|family|travel|appointment|exercise|meal|sleep|chore|other",
   "start_time_local": "ISO local datetime or null",
   "end_time_local": "ISO local datetime or null",
   "timezone": "IANA timezone or Asia/Kolkata",
   "notes": "string"
 }},
 "commitment_id": "known ID or null"
}}
For unknown fields use null or empty lists. Only populate preference fields explicitly supplied by the user.
Known preferences: {json.dumps((profile or {}).get("preferences", {}), ensure_ascii=False)}
User message: {message}
"""
        response = llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        raw = str(content).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        extracted = json.loads(raw)
        if not isinstance(extracted, dict):
            raise ValueError("Groq returned a non-object response")
        allowed = {
            "generate_plan", "update_preferences", "add_commitment",
            "list_commitments", "delete_commitment", "show_saved_plan", "help",
        }
        if extracted.get("intent") not in allowed:
            extracted["intent"] = "help"
        return extracted
    except Exception:
        # A provider outage or malformed response must not block basic help.
        return _fallback_extract(message)


def _format_plan(plan: list[dict[str, Any]], commitments: list[dict[str, Any]] | None = None) -> str:
    """Render recommendations as a concise, human-friendly viewing plan."""
    if not plan:
        return (
            "I couldn't find a suitable match in that date range. Your saved plan is still available, "
            "but it has no recommendations. The local fixtures are simulated. Try another date range "
            "or ask me to show your saved plan."
        )
    lines = [
        "Here’s a viewing plan that takes your preferences and schedule into account.",
        "These are simulated fixtures, not verified real-world schedules.",
        "",
    ]
    busy = commitments or []
    for index, item in enumerate(plan, 1):
        teams = item.get("match_name", "Match")
        date_label = item.get("match_date", "Date not available")
        start = item.get("start_time", "")
        option = item.get("viewing_option", "unavailable")
        windows = item.get("available_viewing_windows", []) or []
        reasons = item.get("recommendation_reasons", []) or []
        lines.append(f"**{index}. {teams}**")
        lines.append(f"📅 {date_label}" + (f" · {start}" if start else ""))
        if option in {"watch_full", "live"}:
            lines.append("✅ This looks like a good option for watching the full match, based on your saved commitments.")
        elif option == "watch_partial":
            useful = max(windows, key=lambda w: int(w.get("duration_minutes", 0)), default=None)
            if useful:
                lines.append(f"🕒 You may be able to watch part of it during a free window ({useful.get('duration_minutes')} minutes).")
            else:
                lines.append("🕒 You may be able to watch part of the match.")
        elif option == "catch_up":
            lines.append("▶️ This fixture is marked as completed in the planning data; consider a replay or highlights if available.")
        else:
            lines.append("⚠️ This match may clash with your schedule. Consider highlights or another fixture.")
        if reasons and reasons != ["No explicit preference matched"]:
            lines.append("Why it fits: " + ", ".join(reasons) + ".")
        # Offer practical work planning advice when a commitment is labelled as work/study.
        related = [c for c in busy if str(c.get("commitment_type", "other")).lower() in {"work", "study", "class", "meeting"}]
        if related and option in {"watch_partial", "unavailable"}:
            lines.append("Work tip: keep fixed work/classes unchanged. If the task is flexible, move a small task to a free period before or after the match; don't schedule work over a fixed commitment.")
        lines.append("")
    lines.append("Want me to adjust this around a work deadline, class, travel, family event, workout, or another commitment?")
    return "\n".join(lines).strip()


def build_planning_graph(repository: PlanningRepository | None = None):
    """Build a compiled LangGraph. Repository may be injected for tests."""
    if StateGraph is None:
        raise RuntimeError(
            "LangGraph is not installed. Run: python -m pip install langgraph"
        ) from _LANGGRAPH_IMPORT_ERROR

    repo = repository or PlanningRepository()

    def load_context(state: PlanningState) -> dict[str, Any]:
        profile = repo.get_profile(state["profile_id"])
        if profile is None:
            # Prevent persisting an error into any caller-supplied session.
            return {
                "error": f"Profile not found: {state['profile_id']}",
                "session_id": "",
            }
        session_id = state.get("session_id")
        session = repo.get_session(session_id) if session_id else None
        if session is None:
            session = repo.create_session(state["profile_id"])
            session_id = session["session_id"]
        elif session["profile_id"] != state["profile_id"]:
            # Do not retain the foreign session ID: the response must never be
            # written into another profile's conversation.
            return {
                "error": "The conversation session does not belong to this profile.",
                "session_id": "",
            }

        repo.add_message(session_id, "user", state["message"])
        commitments = repo.list_commitments(state["profile_id"])
        return {
            "profile": profile,
            "session_id": session_id,
            "commitments": commitments,
        }

    def extract_node(state: PlanningState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        extracted = extract_intent(state["message"], state.get("profile"))
        intent = extracted.get("intent", "help")
        updates: dict[str, Any] = {"extracted": extracted, "intent": intent}
        if intent == "generate_plan":
            start_date = extracted.get("start_date")
            end_date = extracted.get("end_date") or start_date
            if not start_date or not end_date:
                updates["needs_clarification"] = True
                updates["response"] = (
                    "What date range should I use? Please provide a start and end date, "
                    "for example 2026-10-14 to 2026-10-20."
                )
            else:
                try:
                    date.fromisoformat(start_date)
                    date.fromisoformat(end_date)
                    if end_date < start_date:
                        raise ValueError("End date is before start date.")
                    updates.update({
                        "start_date": start_date,
                        "end_date": end_date,
                        "needs_clarification": False,
                    })
                except (TypeError, ValueError):
                    updates["needs_clarification"] = True
                    updates["response"] = "Those dates are invalid. Please use YYYY-MM-DD."
        elif intent == "add_commitment":
            commitment = extracted.get("commitment") or {}
            required = ("title", "start_time_local", "end_time_local")
            missing = [key for key in required if not commitment.get(key)]
            if missing:
                updates["needs_clarification"] = True
                updates["response"] = (
                    "Please share the activity name, type (work, meeting, class, study, family, travel, appointment, exercise, meal, sleep, chore, or other), start date/time, and end date/time. Include a timezone if it isn't India time."
                )
        elif intent == "update_preferences":
            preferences = extracted.get("preferences") or {}
            valid = {
                key: value for key, value in preferences.items()
                if key in PREFERENCE_KEYS and isinstance(value, list)
            }
            if not any(valid.values()):
                updates["needs_clarification"] = True
                updates["response"] = (
                    "Which preference would you like to save? For example, favourite "
                    "team, favourite player, tournament, or match format."
                )
        return updates

    def execute_node(state: PlanningState) -> dict[str, Any]:
        if state.get("error"):
            return {"response": state["error"]}
        if state.get("needs_clarification"):
            return {}
        extracted = state.get("extracted", {})
        intent = state.get("intent", "help")
        if intent == "greeting":
            return {
                "response": (
                    "Hi! 👋 Welcome to MatchPulse AI.\n\n"
                    "I can help you plan cricket viewing around your work, studies, "
                    "and personal commitments.\n\n"
                    "You can ask me to:\n"
                    "- Show matches for a date range\n"
                    "- Save your favourite teams or players\n"
                    "- Add or view commitments\n"
                    "- Generate or retrieve your personalised plan\n\n"
                    "What would you like to do first?"
                )
            }
        intent = state.get("intent", "help")
        profile = state["profile"]
        profile_id = state["profile_id"]
        session_id = state["session_id"]

        if intent == "generate_plan":
            saved_preferences = profile.get("preferences", {})
            plan = generate_personalised_plan(
                saved_preferences,
                state.get("commitments", []),
                state["start_date"],
                state["end_date"],
                top_n=26,
            )
            # If the fan selected favourite teams and matching fixtures exist,
            # show those first and exclude unrelated teams from this shortlist.
            favourite_teams = {str(team).strip().casefold() for team in saved_preferences.get("favorite_teams", []) if str(team).strip()}
            if favourite_teams:
                preferred = [item for item in plan if any(team in {str(item.get("team_a", "")).casefold(), str(item.get("team_b", "")).casefold()} for team in favourite_teams) or any(team in str(item.get("match_name", "")).casefold() for team in favourite_teams)]
                if preferred:
                    plan = preferred
            plan = plan[:5]
            saved = repo.save_plan(
                profile_id, state["start_date"], state["end_date"], plan,
                session_id=session_id,
            )
            return {
                "plan": plan,
                "response": _format_plan(plan, state.get("commitments", [])) + f"\n\nPlan saved. Reference: `{saved['plan_id']}`",
            }

        if intent == "update_preferences":
            requested = extracted.get("preferences") or {}
            existing = profile.get("preferences", {})
            merged = dict(existing)
            for key, values in requested.items():
                if key in PREFERENCE_KEYS and isinstance(values, list):
                    merged[key] = list(dict.fromkeys(
                        [*merged.get(key, []), *values]
                    ))
            updated = repo.update_profile(profile_id, preferences=merged)
            return {
                "profile": updated,
                "response": "Preferences saved successfully.",
            }

        if intent == "add_commitment":
            item = extracted["commitment"]
            try:
                repo.add_commitment(
                    profile_id=profile_id,
                    title=item["title"],
                    start_time_local=item["start_time_local"],
                    end_time_local=item["end_time_local"],
                    timezone=item.get("timezone") or "Asia/Kolkata",
                    notes=item.get("notes") or "",
                    commitment_type=item.get("commitment_type") or "other",
                )
            except (ValueError, KeyError) as exc:
                return {
                    "response": f"I couldn't save that commitment: {exc}. Please check the details."
                }
            kind = (item.get("commitment_type") or "other").replace("_", " ").title()
            return {"response": f"Done — I’ve added your {kind.lower()} commitment, **{item['title']}**. I’ll consider it when suggesting match times and free viewing windows."}

        if intent == "list_commitments":
            commitments = repo.list_commitments(profile_id)
            if not commitments:
                return {"response": "You have no saved commitments yet."}
            lines = ["Your saved commitments:"]
            for item in commitments:
                kind = item.get("commitment_type", "other").replace("_", " ").title()
                lines.append(
                    f"- **{item['title']}** ({kind}): {item['start_time_local']} to "
                    f"{item['end_time_local']} ({item['timezone']})"
                )
            return {"response": "\n".join(lines)}

        if intent == "delete_commitment":
            commitment_id = extracted.get("commitment_id")
            if not commitment_id:
                return {
                    "needs_clarification": True,
                    "response": "Please provide the commitment ID you want to delete.",
                }
            deleted = repo.delete_commitment(commitment_id, profile_id)
            return {"response": "Commitment deleted." if deleted else "I couldn't find that commitment for this profile."}

        if intent == "show_saved_plan":
            plans = repo.list_saved_plans(profile_id)
            if not plans:
                return {"response": "You don't have a saved plan yet. Ask me to generate one first."}
            latest = plans[0]
            if latest["plan"]:
                saved_text = _format_plan(latest["plan"], repo.list_commitments(profile_id))
            else:
                saved_text = (
                    f"Your latest saved plan covers {latest['start_date']} to "
                    f"{latest['end_date']}, but it contains no matching fixtures. "
                    "The fixture dataset is synthetic. Generate a new plan for a "
                    "date range covered by the local dataset."
                )
            return {
                "plan": latest["plan"],
                "response": saved_text + f"\n\nSaved on: {latest['created_at']}\nPlan ID: {latest['plan_id']}",
            }

        return {
            "response": (
                "I can help you save cricket preferences, add or list commitments, "
                "and generate a personalised viewing plan. Try: "
                "'Show matches from 2026-10-14 to 2026-10-20'. "
                "The current fixture dataset is simulated."
            )
        }

    def persist_response(state: PlanningState) -> dict[str, Any]:
        if state.get("response") and state.get("session_id"):
            repo.add_message(
                state["session_id"], "assistant", state["response"],
                metadata={
                    "intent": state.get("intent", "unknown"),
                    "needs_clarification": state.get("needs_clarification", False),
                },
            )
        return {}

    def route_after_load(state: PlanningState) -> str:
        return "respond_error" if state.get("error") else "extract"

    def respond_error(state: PlanningState) -> dict[str, Any]:
        return {"response": state.get("error", "Unknown planning error.")}

    def route_after_extract(state: PlanningState) -> str:
        return "execute"

    graph = StateGraph(PlanningState)
    graph.add_node("load_context", load_context)
    graph.add_node("extract", extract_node)
    graph.add_node("execute", execute_node)
    graph.add_node("respond_error", respond_error)
    graph.add_node("persist_response", persist_response)
    graph.add_edge(START, "load_context")
    graph.add_conditional_edges(
        "load_context",
        route_after_load,
        {"extract": "extract", "respond_error": "respond_error"},
    )
    graph.add_edge("extract", "execute")
    graph.add_edge("execute", "persist_response")
    graph.add_edge("respond_error", "persist_response")
    graph.add_edge("persist_response", END)
    return graph.compile()


def run_planning_message(
    profile_id: str,
    message: str,
    session_id: str | None = None,
    repository: PlanningRepository | None = None,
) -> dict[str, Any]:
    """Run one conversational turn and return the final graph state."""
    if not message or not message.strip():
        raise ValueError("message must not be empty")
    repo = repository or PlanningRepository()
    graph = build_planning_graph(repo)
    initial: PlanningState = {
        "profile_id": profile_id,
        "message": message.strip(),
    }
    if session_id:
        initial["session_id"] = session_id
    return graph.invoke(initial)
