from datetime import date, datetime
from zoneinfo import ZoneInfo
from src.assistant.personalisation_response_formatter import create_personalised_plan_response

TIMEZONE = "Asia/Kolkata"


def ask_list(prompt: str) -> list[str]:
    answer = input(prompt).strip()
    if not answer or answer.casefold() in {"none", "skip"}:
        return []
    if answer.casefold() in {"exit", "quit", "cancel"}:
        raise KeyboardInterrupt
    return [item.strip() for item in answer.split(",") if item.strip()]


def ask_date(prompt: str) -> date:
    while True:
        answer = input(prompt).strip()
        if answer.casefold() in {"exit", "quit", "cancel"}:
            raise KeyboardInterrupt
        try:
            return date.fromisoformat(answer)
        except ValueError:
            print("Enter a valid date in YYYY-MM-DD format, or type 'cancel'.")


def ask_time(prompt: str) -> str:
    while True:
        answer = input(prompt).strip()
        if answer.casefold() in {"exit", "quit", "cancel"}:
            raise KeyboardInterrupt
        try:
            return datetime.strptime(answer, "%H:%M").strftime("%H:%M")
        except ValueError:
            print("Enter a valid time, such as 09:00 or 18:30, or type 'cancel'.")


def collect_commitments(start_date: date, end_date: date) -> list[dict]:
    commitments = []
    timezone = ZoneInfo(TIMEZONE)
    print("\\nAdd work, class, or personal commitments. Type 'done' when finished.")
    while True:
        title = input("\\nCommitment name: ").strip()
        if title.casefold() in {"done", "exit", "menu", "cancel"}:
            break
        if not title:
            print("Enter a name or type 'done'.")
            continue
        try:
            commitment_date = ask_date("Date (YYYY-MM-DD): ")
            if not start_date <= commitment_date <= end_date:
                print("The date must be within your planning period.")
                continue
            start_time = ask_time("Start time (HH:MM): ")
            end_time = ask_time("End time (HH:MM): ")
        except KeyboardInterrupt:
            print("Commitment entry cancelled.")
            break
        start = datetime.combine(commitment_date, datetime.strptime(start_time, "%H:%M").time(), tzinfo=timezone)
        end = datetime.combine(commitment_date, datetime.strptime(end_time, "%H:%M").time(), tzinfo=timezone)
        if end <= start:
            print("End time must be later than start time. Overnight commitments are not supported.")
            continue
        commitments.append({"title": title, "start_time_local": start.isoformat(timespec="minutes"), "end_time_local": end.isoformat(timespec="minutes"), "timezone": TIMEZONE})
        print("Commitment added.")
    return commitments


def run_personalisation_flow() -> None:
    print("\\n=== MATCHPULSE AI: PERSONALISED CRICKET PLANNER ===")
    print("Type 'cancel' or 'exit' at any prompt to leave the flow.")
    try:
        favorite_teams = ask_list("Favourite teams (comma-separated, or skip): ")
        favorite_players = ask_list("Favourite players (comma-separated, or skip): ")
        favorite_tournaments = ask_list("Favourite tournaments (comma-separated, or skip): ")
        preferred_match_types = ask_list("Preferred formats, e.g. T20, ODI (comma-separated, or skip): ")
        start_date = ask_date("\\nPlanning start date (YYYY-MM-DD): ")
        end_date = ask_date("Planning end date (YYYY-MM-DD): ")
        if end_date < start_date:
            print("End date cannot be earlier than start date.")
            return
        profile = {"favorite_teams": favorite_teams, "favorite_players": favorite_players, "favorite_tournaments": favorite_tournaments, "preferred_match_types": preferred_match_types, "important_match_ids": []}
        commitments = collect_commitments(start_date, end_date)
        print("\\n" + create_personalised_plan_response(profile, commitments, start_date.isoformat(), end_date.isoformat()))
    except KeyboardInterrupt:
        print("\\nReturning from Personalised Planning.")


if __name__ == "__main__":
    run_personalisation_flow()
