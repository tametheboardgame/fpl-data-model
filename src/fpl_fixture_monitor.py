from __future__ import annotations

from typing import Any


def integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _fixture_for_team(row: dict[str, Any], team_id: int) -> dict[str, Any]:
    home_team_id = integer(row.get("home_team_id"))
    is_home = home_team_id == team_id
    return {
        "fixture_id": integer(row.get("fixture_id")) or row.get("fixture_id"),
        "kickoff_time": row.get("kickoff_time"),
        "is_home": is_home,
        "opponent_team_id": (
            integer(row.get("away_team_id"))
            if is_home
            else integer(row.get("home_team_id"))
        ),
        "opponent": row.get("away_team") if is_home else row.get("home_team"),
    }


def build_fixture_schedule_monitor(
    fixtures: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    current_gameweek: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    """Summarise confirmed future Blank/Double Gameweek structure.

    The monitor uses the official FPL fixture-to-Gameweek assignment as the source
    of truth. A fixture with no assigned Gameweek is retained as an unscheduled
    fixture so postponements remain visible before they are rescheduled.
    """

    team_by_id = {
        integer(team.get("team_id")): str(team.get("name") or team.get("team_name") or "")
        for team in teams
        if integer(team.get("team_id"))
    }
    team_ids = sorted(team_by_id)

    next_event = current_gameweek.get("next") or {}
    current_event = current_gameweek.get("current") or {}
    monitored_from = integer(next_event.get("id"))
    if not monitored_from:
        monitored_from = integer(current_event.get("id"))
    if not monitored_from:
        monitored_from = 1

    scheduled_by_gameweek: dict[int, list[dict[str, Any]]] = {}
    unscheduled: list[dict[str, Any]] = []
    max_scheduled_gameweek = 0

    for row in fixtures:
        gameweek = integer(row.get("gameweek"))
        if gameweek:
            scheduled_by_gameweek.setdefault(gameweek, []).append(row)
            max_scheduled_gameweek = max(max_scheduled_gameweek, gameweek)
            continue
        if str(row.get("finished")).strip().lower() in {"true", "1", "yes"}:
            continue
        unscheduled.append(
            {
                "fixture_id": integer(row.get("fixture_id")) or row.get("fixture_id"),
                "kickoff_time": row.get("kickoff_time"),
                "home_team_id": integer(row.get("home_team_id")),
                "home_team": row.get("home_team"),
                "away_team_id": integer(row.get("away_team_id")),
                "away_team": row.get("away_team"),
            }
        )

    final_gameweek = max(max_scheduled_gameweek, monitored_from)
    special_gameweeks: list[dict[str, Any]] = []

    for gameweek in range(monitored_from, final_gameweek + 1):
        rows = scheduled_by_gameweek.get(gameweek, [])
        fixtures_by_team: dict[int, list[dict[str, Any]]] = {
            team_id: [] for team_id in team_ids
        }
        for row in rows:
            home_team_id = integer(row.get("home_team_id"))
            away_team_id = integer(row.get("away_team_id"))
            if home_team_id in fixtures_by_team:
                fixtures_by_team[home_team_id].append(row)
            if away_team_id in fixtures_by_team:
                fixtures_by_team[away_team_id].append(row)

        blank_team_ids = sorted(
            team_id for team_id, team_rows in fixtures_by_team.items() if len(team_rows) == 0
        )
        double_team_ids = sorted(
            team_id for team_id, team_rows in fixtures_by_team.items() if len(team_rows) > 1
        )
        if not blank_team_ids and not double_team_ids:
            continue

        if blank_team_ids and double_team_ids:
            event_type = "blank_and_double"
        elif double_team_ids:
            event_type = "double"
        else:
            event_type = "blank"

        double_teams = []
        for team_id in double_team_ids:
            team_rows = fixtures_by_team[team_id]
            double_teams.append(
                {
                    "team_id": team_id,
                    "team_name": team_by_id.get(team_id),
                    "fixture_count": len(team_rows),
                    "fixtures": [
                        _fixture_for_team(row, team_id)
                        for row in sorted(
                            team_rows,
                            key=lambda item: (
                                str(item.get("kickoff_time") or ""),
                                integer(item.get("fixture_id")),
                            ),
                        )
                    ],
                }
            )

        special_gameweeks.append(
            {
                "gameweek": gameweek,
                "type": event_type,
                "blank_team_ids": blank_team_ids,
                "blank_team_names": [team_by_id.get(team_id) for team_id in blank_team_ids],
                "blank_team_count": len(blank_team_ids),
                "double_team_ids": double_team_ids,
                "double_team_names": [team_by_id.get(team_id) for team_id in double_team_ids],
                "double_team_count": len(double_team_ids),
                "double_teams": double_teams,
            }
        )

    double_gameweeks = [
        row for row in special_gameweeks if integer(row.get("double_team_count")) > 0
    ]
    blank_gameweeks = [
        row for row in special_gameweeks if integer(row.get("blank_team_count")) > 0
    ]

    return {
        "generated_at": generated_at,
        "status": "ready" if team_ids else "teams_unavailable",
        "source": "official_fpl_fixture_schedule",
        "monitored_from_gameweek": monitored_from,
        "monitored_through_gameweek": final_gameweek,
        "next_double_gameweek": (
            integer(double_gameweeks[0].get("gameweek")) if double_gameweeks else None
        ),
        "next_blank_gameweek": (
            integer(blank_gameweeks[0].get("gameweek")) if blank_gameweeks else None
        ),
        "double_gameweeks": double_gameweeks,
        "blank_gameweeks": blank_gameweeks,
        "special_gameweeks": special_gameweeks,
        "unscheduled_fixture_count": len(unscheduled),
        "unscheduled_fixtures": sorted(
            unscheduled,
            key=lambda row: (
                str(row.get("kickoff_time") or ""),
                integer(row.get("fixture_id")),
            ),
        ),
        "principle": (
            "Blank/Double structure is confirmed only from the official FPL fixture "
            "Gameweek assignment. Unassigned fixtures remain visible as unscheduled "
            "until FPL places them into a Gameweek."
        ),
    }
