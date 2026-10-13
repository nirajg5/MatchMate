
from __future__ import annotations

import os
import streamlit as st

from src.assistant.planning_repository import PlanningRepository
from src.assistant.personalisation_graph import run_planning_message

st.set_page_config(
    page_title="MatchPulse AI | Personalised Planning",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)

PITCH = "#17382E"
PITCH_LIGHT = "#234A3D"
AMBER = "#F2B134"
CREAM = "#F7F5EF"
INK = "#17231F"
MUTED = "#66756F"


st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@500;600;700&display=swap');

    :root {{
        color-scheme: light;
    }}

    html, body, [class*="css"] {{
        font-family: 'Barlow', sans-serif;
        color: {INK} !important;
    }}

    .stApp {{
        background: {CREAM} !important;
        color: {INK} !important;
    }}

    [data-testid="stHeader"] {{
        background: {CREAM} !important;
    }}

    /* Original dark-green sidebar */
    [data-testid="stSidebar"] {{
        background: {PITCH} !important;
    }}

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
        color: #FFFFFF !important;
        opacity: 1 !important;
    }}

    /* Sidebar inputs: white background, dark text */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
        background: #FFFFFF !important;
        color: #17231F !important;
        -webkit-text-fill-color: #17231F !important;
        border: 1px solid #C8D2CD !important;
        border-radius: 8px !important;
    }}

    [data-testid="stSidebar"] [data-baseweb="select"] * {{
        color: #17231F !important;
    }}

    /* Header banner */
    .hero {{
        background: linear-gradient(120deg, {PITCH}, {PITCH_LIGHT});
        padding: 1.45rem 1.6rem;
        border-radius: 18px;
        color: #FFFFFF !important;
        border-bottom: 5px solid {AMBER};
        margin-bottom: 1.1rem;
    }}

    .hero h1 {{
        color: #FFFFFF !important;
        font-family: 'Barlow Condensed', sans-serif;
        font-size: 2.5rem;
        margin: 0;
        letter-spacing: .3px;
    }}

    .hero p {{
        color: #F1F5F2 !important;
        margin: .25rem 0 0 0;
        font-size: 1rem;
    }}

    /* Prototype warning */
    .warning {{
        background: #FFF4D6 !important;
        color: #604600 !important;
        padding: .8rem 1rem;
        border-radius: 10px;
        border: 1px solid #D6B45B;
        margin-bottom: 1rem;
    }}

    .warning * {{
        color: #604600 !important;
        opacity: 1 !important;
    }}

    .section-label {{
        color: {PITCH} !important;
        font-weight: 700;
        letter-spacing: .5px;
    }}

    /* Buttons */
    div.stButton > button,
    div.stFormSubmitButton > button {{
        background: {PITCH} !important;
        color: #FFFFFF !important;
        border: 1px solid {PITCH} !important;
        border-radius: 10px;
        font-weight: 600;
        min-height: 2.6rem;
        opacity: 1 !important;
    }}

    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover {{
        background: {PITCH_LIGHT} !important;
        color: #FFFFFF !important;
        border: 1px solid {AMBER} !important;
    }}

    /* Chat messages: white cards with dark, readable text */
    [data-testid="stChatMessage"] {{
        background: #FFFFFF !important;
        border: 1px solid #C8D2CD !important;
        border-radius: 14px !important;
        padding: 1rem !important;
        margin: .6rem 0 !important;
        box-shadow: 0 2px 5px rgba(23, 35, 31, .06);
        opacity: 1 !important;
    }}

    [data-testid="stChatMessage"] *,
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] strong,
    [data-testid="stChatMessage"] em,
    [data-testid="stChatMessage"] span,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {{
        color: #17231F !important;
        -webkit-text-fill-color: #17231F !important;
        opacity: 1 !important;
    }}

    [data-testid="stChatMessage"] code {{
        background: #EEF2EF !important;
        color: #17231F !important;
        border: 1px solid #C8D2CD !important;
        border-radius: 4px;
        padding: .1rem .3rem;
    }}

    /* Chat input: white, bordered, dark typing and placeholder text */
    [data-testid="stChatInput"],
    [data-testid="stChatInput"] > div,
    [data-testid="stChatInput"] textarea {{
        background: #FFFFFF !important;
        color: #17231F !important;
        -webkit-text-fill-color: #17231F !important;
        border: 1px solid #82958B !important;
        border-radius: 10px !important;
        opacity: 1 !important;
    }}

    [data-testid="stChatInput"] textarea::placeholder {{
        color: #52615B !important;
        -webkit-text-fill-color: #52615B !important;
        opacity: 1 !important;
    }}

    [data-testid="stChatInput"] button {{
        background: #FFFFFF !important;
        color: {PITCH} !important;
        opacity: 1 !important;
    }}

    [data-testid="stChatInput"] button svg {{
        color: {PITCH} !important;
        fill: {PITCH} !important;
    }}

    /* Main text, labels, headings and right-side metrics */
    [data-testid="stMain"] h1,
    [data-testid="stMain"] h2,
    [data-testid="stMain"] h3,
    [data-testid="stMain"] h4,
    [data-testid="stMain"] p,
    [data-testid="stMain"] li,
    [data-testid="stMain"] label,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"] {{
        color: #17231F !important;
        opacity: 1 !important;
    }}

    [data-testid="stMetric"] {{
        background: #FFFFFF !important;
        border: 1px solid #C8D2CD !important;
        border-radius: 10px;
        padding: .75rem;
    }}

    [data-testid="stCaptionContainer"] p,
    .small-note {{
        color: #52615B !important;
        opacity: 1 !important;
        font-size: .88rem;
    }}

    /* Other form controls */
    [data-testid="stMain"] input,
    [data-testid="stMain"] textarea,
    [data-testid="stMain"] [data-baseweb="select"] > div {{
        background: #FFFFFF !important;
        color: #17231F !important;
        -webkit-text-fill-color: #17231F !important;
        border-color: #C8D2CD !important;
    }}

    [data-testid="stMain"] [data-baseweb="select"] * {{
        color: #17231F !important;
    }}

    [data-testid="stAlert"] {{
        border: 1px solid #C8D2CD !important;
        border-radius: 10px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

repo = PlanningRepository()


def _ensure_session() -> None:
    if "planning_profile_id" not in st.session_state:
        profile = repo.create_profile(
            display_name="Cricket Fan",
            preferences={
                "favorite_teams": [],
                "favorite_players": [],
                "favorite_tournaments": [],
                "preferred_match_types": [],
                "important_match_ids": [],
            },
        )
        st.session_state.planning_profile_id = profile["profile_id"]
        session = repo.create_session(profile["profile_id"])
        st.session_state.planning_session_id = session["session_id"]
        st.session_state.planning_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hi! I can help you plan cricket viewing around your schedule. "
                    "Tell me your preferences, add commitments, or ask for a plan "
                    "using dates such as `2026-10-14` to `2026-10-20`."
                ),
            }
        ]


def _new_conversation() -> None:
    session = repo.create_session(st.session_state.planning_profile_id)
    st.session_state.planning_session_id = session["session_id"]
    st.session_state.planning_messages = [
        {
            "role": "assistant",
            "content": "New conversation started. What would you like to plan?",
        }
    ]


_ensure_session()
profile = repo.get_profile(st.session_state.planning_profile_id)
if profile is None:
    st.error("The saved profile could not be loaded. Refresh the page to create a new one.")
    st.stop()

st.markdown(
    """
    <div class="hero">
      <h1>🏏 MatchPulse AI</h1>
      <p>Personalised Planning · Plan your cricket viewing around real life</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="warning"><strong>Prototype data notice:</strong> The fixtures in this '
    'project are simulated examples, not verified upcoming cricket matches. '
    'Recommendations and times are based on that local test dataset.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Personalised Planning")
    st.caption("Your preferences and commitments are stored locally in SQLite.")
    display_name = st.text_input("Your name", value=profile.get("display_name", "Cricket Fan"))
    if st.button("Save name", use_container_width=True):
        repo.update_profile(profile["profile_id"], display_name=display_name)
        st.success("Name saved.")

    st.divider()
    st.markdown("### Quick prompts")
    quick_prompts = [
        "Show my commitments",
        "Show my saved plan",
        "Help",
    ]
    for index, prompt in enumerate(quick_prompts):
        if st.button(prompt, key=f"quick_prompt_{index}", use_container_width=True):
            st.session_state.pending_planning_prompt = prompt

    st.divider()
    if st.button("＋ New conversation", use_container_width=True):
        _new_conversation()
        st.rerun()

    st.markdown("---")
    st.caption("Architecture: Streamlit · LangGraph · Groq · SQLite")
    st.caption("Your existing app.py is not modified by this interface.")

left, right = st.columns([2.1, 1], gap="large")
with left:
    st.markdown("### Planning conversation")
    for message in st.session_state.planning_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    typed_message = st.chat_input(
        "Ask for a plan, update preferences, or manage commitments…"
    )

    pending = st.session_state.pop("pending_planning_prompt", None)
    user_message = typed_message or pending
    if user_message:
        st.session_state.planning_messages.append(
            {"role": "user", "content": user_message}
        )
        with st.chat_message("user"):
            st.markdown(user_message)

        with st.chat_message("assistant"):
            with st.spinner("Working on your plan…"):
                try:
                    result = run_planning_message(
                        profile_id=st.session_state.planning_profile_id,
                        session_id=st.session_state.planning_session_id,
                        message=user_message,
                        repository=repo,
                    )
                    response_text = result.get(
                        "response", "I couldn't produce a response. Please try again."
                    )
                    if result.get("session_id"):
                        st.session_state.planning_session_id = result["session_id"]
                except Exception as exc:
                    response_text = (
                        "Something went wrong while processing that request. "
                        "Check the terminal for details, then try again. "
                        f"\n\n`{type(exc).__name__}: {exc}`"
                    )
                st.markdown(response_text)

        st.session_state.planning_messages.append(
            {"role": "assistant", "content": response_text}
        )

with right:
    st.markdown("### Your saved data")
    commitments = repo.list_commitments(profile["profile_id"])
    saved_plans = repo.list_saved_plans(profile["profile_id"])
    metric1, metric2 = st.columns(2)
    metric1.metric("Commitments", len(commitments))
    metric2.metric("Saved plans", len(saved_plans))

    st.markdown("#### Preferences")
    prefs = profile.get("preferences", {})
    pref_fields = [
        ("Favourite teams", "favorite_teams"),
        ("Favourite players", "favorite_players"),
        ("Tournaments", "favorite_tournaments"),
        ("Match formats", "preferred_match_types"),
    ]
    for label, key in pref_fields:
        values = prefs.get(key, [])
        st.markdown(f"**{label}**")
        st.write(", ".join(values) if values else "Not set")

    st.markdown("#### Upcoming commitments")
    if not commitments:
        st.caption("No commitments saved yet.")
    else:
        for item in commitments[:5]:
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.caption(
                    f"{item['start_time_local']} – {item['end_time_local']} "
                    f"({item['timezone']})"
                )
                st.caption(f"ID: `{item['commitment_id']}`")

    st.markdown("#### Recent saved plans")
    if not saved_plans:
        st.caption("No saved plans yet.")
    else:
        for item in saved_plans[:3]:
            with st.container(border=True):
                st.markdown(f"**{item['start_date']} → {item['end_date']}**")
                st.caption(f"{len(item['plan'])} recommendations")
                st.caption(f"Saved: {item['created_at']}")
