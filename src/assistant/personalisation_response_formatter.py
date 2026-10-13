from typing import Any
from src.assistant.personalisation_engine import generate_personalised_plan


def create_personalised_plan_response(
    profile: dict[str, Any], commitments: list[dict[str, Any]],
    start_date: str, end_date: str, top_n: int = 5,
) -> str:
    """Generate and format a personalised cricket viewing plan."""
    try:
        plan = generate_personalised_plan(
            profile=profile, commitments=commitments,
            start_date=start_date, end_date=end_date, top_n=top_n,
        )
    except (ValueError, FileNotFoundError) as exc:
        return f"I couldn't generate your plan: {exc}"
    if not plan:
        return f"I couldn't find any fixtures between {start_date} and {end_date} in the available dataset. The fixture dataset is simulated."
    lines = ["YOUR PERSONALISED CRICKET PLAN", f"Planning period: {start_date} to {end_date}", "", "Note: fixtures in this prototype are simulated examples, not verified real-world schedules.", ""]
    for index, match in enumerate(plan, start=1):
        lines.extend([
            f"{index}. {match.get('match_name', 'Match')}",
            f"   Date: {match.get('match_date', 'Not available')}",
            f"   Start: {match.get('start_time', 'Not available')} ({match.get('timezone', 'Asia/Kolkata')})",
            f"   Format: {match.get('match_type', 'Not available')}",
            f"   Tournament: {match.get('tournament', 'Not available')}",
            f"   Relevance score: {match.get('relevance_score', 0)}/100",
            f"   Viewing recommendation: {str(match.get('viewing_option', 'unavailable')).replace('_', ' ').title()}",
            "   Why recommended: " + "; ".join(match.get('recommendation_reasons', [])),
        ])
        for window in match.get('available_viewing_windows', []) or []:
            lines.append(f"   Available window: {window.get('start')} to {window.get('end')} ({window.get('duration_minutes')} minutes)")
        if match.get('is_simulated', True):
            lines.append("   Note: Fictional test fixture; not a real announced cricket match.")
        lines.append("")
    lines.append("Update your commitments or preferences to generate a revised plan.")
    return "\\n".join(lines)
