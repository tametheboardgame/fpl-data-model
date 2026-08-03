from __future__ import annotations

from collections import Counter
from statistics import fmean
from typing import Any


LAUNCH_VALIDATION_VERSION = "fpl-launch-validation-1.0"
SQUAD_POSITION_LIMITS = {
    "Goalkeeper": 2,
    "Defender": 5,
    "Midfielder": 5,
    "Forward": 3,
}
STARTING_POSITION_LIMITS = {
    "Goalkeeper": (1, 1),
    "Defender": (3, 5),
    "Midfielder": (2, 5),
    "Forward": (1, 3),
}


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def _check(passed: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "observed": observed, "expected": expected}


def _issue(code: str, message: str, severity: str = "high") -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def _gameweek_one_points(
    horizons: list[dict[str, Any]],
    fixture_projections: list[dict[str, Any]],
) -> dict[int, float]:
    horizon_points = {
        integer(row.get("player_id")): number(row.get("expected_points_next_1"))
        for row in horizons
        if integer(row.get("player_id"))
    }
    if any(value > 0 for value in horizon_points.values()):
        return horizon_points
    gameweeks = sorted(
        {
            integer(row.get("gameweek"))
            for row in fixture_projections
            if integer(row.get("gameweek"))
        }
    )
    if not gameweeks:
        return horizon_points
    first = gameweeks[0]
    points: dict[int, float] = {}
    for row in fixture_projections:
        if integer(row.get("gameweek")) != first:
            continue
        player_id = integer(row.get("player_id"))
        points[player_id] = points.get(player_id, 0) + number(
            row.get("expected_points")
        )
    return points


def _latest_past_seasons(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("season_name") or "")):
        code = integer(row.get("player_code"))
        if code:
            latest[code] = row
    return latest


def validate_launch_plan(
    players: list[dict[str, Any]],
    horizons: list[dict[str, Any]],
    fixture_projections: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    recommended: dict[str, Any],
    route: dict[str, Any],
    past_seasons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    canonical = {
        integer(row.get("player_id")): row
        for row in players
        if integer(row.get("player_id"))
    }
    points = _gameweek_one_points(horizons, fixture_projections)
    issues: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}

    mapping_mismatches = []
    for collection, rows in (
        ("horizon", horizons),
        ("fixture_projection", fixture_projections),
    ):
        for row in rows:
            player_id = integer(row.get("player_id"))
            player = canonical.get(player_id)
            if not player:
                mapping_mismatches.append(
                    {"collection": collection, "player_id": player_id, "field": "player_id"}
                )
                continue
            for field in ("team_id", "position"):
                if row.get(field) in {None, ""}:
                    continue
                if str(row.get(field)) != str(player.get(field)):
                    mapping_mismatches.append(
                        {
                            "collection": collection,
                            "player_id": player_id,
                            "field": field,
                            "observed": row.get(field),
                            "expected": player.get(field),
                        }
                    )
    checks["canonical_player_mapping"] = _check(
        not mapping_mismatches,
        len(mapping_mismatches),
        0,
    )
    if mapping_mismatches:
        issues.append(
            _issue(
                "player_mapping_mismatch",
                f"{len(mapping_mismatches)} projection rows do not match the official player, club or position mapping.",
            )
        )

    positive = [value for value in points.values() if value > 0]
    attackers = [
        points.get(player_id, 0)
        for player_id, row in canonical.items()
        if row.get("position") in {"Midfielder", "Forward"}
    ]
    defenders = [
        points.get(player_id, 0)
        for player_id, row in canonical.items()
        if row.get("position") == "Defender"
    ]
    premium_attackers = [
        points.get(player_id, 0)
        for player_id, row in canonical.items()
        if row.get("position") in {"Midfielder", "Forward"}
        and number(row.get("price")) >= 10
    ]
    top_overall = max(positive, default=0)
    top_attacker = max(attackers, default=0)
    top_defender = max(defenders, default=0)
    top_premium_attacker = max(premium_attackers, default=0)
    checks["expected_points_scale"] = _check(
        top_overall >= 4 and top_attacker >= 4,
        {
            "top_overall": round(top_overall, 3),
            "top_attacker": round(top_attacker, 3),
            "top_defender": round(top_defender, 3),
        },
        {"top_overall_minimum": 4, "top_attacker_minimum": 4},
    )
    if not checks["expected_points_scale"]["passed"]:
        issues.append(
            _issue(
                "compressed_projection_scale",
                "The Gameweek 1 expected-points distribution is implausibly compressed; no recommendation may be marked ready.",
            )
        )

    if premium_attackers:
        premium_passed = (
            top_premium_attacker >= 3.5
            and top_premium_attacker >= 0.85 * top_defender
        )
        checks["premium_attacker_scale"] = _check(
            premium_passed,
            {
                "top_premium_attacker": round(top_premium_attacker, 3),
                "top_defender": round(top_defender, 3),
                "ratio": round(
                    top_premium_attacker / top_defender if top_defender else 0,
                    3,
                ),
            },
            {"minimum_points": 3.5, "minimum_defender_ratio": 0.85},
        )
        if not premium_passed:
            issues.append(
                _issue(
                    "premium_attacker_projection_anomaly",
                    "Premium attackers are projected materially below the leading defenders; captaincy and squad selection require review.",
                )
            )

    evidence_rows = [
        row for row in horizons if row.get("projection_evidence_source")
    ]
    if evidence_rows:
        previous_rows = sum(
            row.get("projection_evidence_source")
            in {"previous_season", "current_and_previous_season"}
            for row in evidence_rows
        )
        coverage = previous_rows / len(evidence_rows)
        checks["previous_season_evidence"] = _check(
            previous_rows >= 100 and coverage >= 0.25,
            {
                "players": previous_rows,
                "coverage": round(coverage, 3),
            },
            {"minimum_players": 100, "minimum_coverage": 0.25},
        )
        if not checks["previous_season_evidence"]["passed"]:
            issues.append(
                _issue(
                    "insufficient_previous_season_evidence",
                    "Too little player-specific previous-season evidence is active for a safe launch projection.",
                )
            )

    latest_past = _latest_past_seasons(past_seasons or [])
    player_code = {
        integer(row.get("player_id")): integer(row.get("player_code"))
        for row in players
    }
    baseline_pairs = []
    for player_id, projected in points.items():
        past = latest_past.get(player_code.get(player_id, 0))
        minutes = number((past or {}).get("minutes"))
        if minutes < 900:
            continue
        baseline_pairs.append(
            (number(past.get("total_points")) * 90 / minutes, projected)
        )
    if len(baseline_pairs) >= 40:
        ordered = sorted(baseline_pairs)
        quartile = max(10, len(ordered) // 4)
        low_mean = fmean(value for _, value in ordered[:quartile])
        high_mean = fmean(value for _, value in ordered[-quartile:])
        checks["historical_baseline_ordering"] = _check(
            high_mean >= low_mean + 0.25,
            {
                "established_players": len(ordered),
                "low_quartile_projection": round(low_mean, 3),
                "high_quartile_projection": round(high_mean, 3),
            },
            {"minimum_quartile_gap": 0.25},
        )
        if not checks["historical_baseline_ordering"]["passed"]:
            issues.append(
                _issue(
                    "historical_baseline_inversion",
                    "Projected returns do not preserve a credible ordering against established previous-season performance.",
                )
            )

    strategy_failures = []
    for variant in strategies:
        squad = variant.get("squad", [])
        starters = variant.get("starting_xi", [])
        bench = variant.get("bench_order", [])
        squad_ids = [integer(row.get("player_id")) for row in squad]
        starter_ids = [integer(row.get("player_id")) for row in starters]
        bench_ids = [integer(row.get("player_id")) for row in bench]
        position_counts = Counter(str(row.get("position")) for row in squad)
        starter_positions = Counter(str(row.get("position")) for row in starters)
        club_counts = Counter(integer(row.get("team_id")) for row in squad)
        captain = integer((variant.get("captain") or {}).get("player_id"))
        vice = integer((variant.get("vice_captain") or {}).get("player_id"))
        valid = (
            len(squad_ids) == len(set(squad_ids)) == 15
            and len(starter_ids) == len(set(starter_ids)) == 11
            and len(bench_ids) == len(set(bench_ids)) == 4
            and set(starter_ids).union(bench_ids) == set(squad_ids)
            and not set(starter_ids).intersection(bench_ids)
            and dict(position_counts) == SQUAD_POSITION_LIMITS
            and max(club_counts.values(), default=0) <= 3
            and number(variant.get("total_cost")) <= 100
            and all(
                lower <= starter_positions.get(position, 0) <= upper
                for position, (lower, upper) in STARTING_POSITION_LIMITS.items()
            )
            and captain in starter_ids
            and vice in starter_ids
            and captain != vice
            and all(player_id in canonical for player_id in squad_ids)
        )
        if not valid:
            strategy_failures.append(variant.get("strategy"))
    checks["strategy_contracts"] = _check(
        not strategy_failures and len(strategies) == 3,
        {"strategies": len(strategies), "failed": strategy_failures},
        {"strategies": 3, "failed": []},
    )
    if not checks["strategy_contracts"]["passed"]:
        issues.append(
            _issue(
                "invalid_strategy_contract",
                "At least one launch strategy is not a legal, complete £100m squad with a valid XI, bench and captaincy pair.",
            )
        )

    captain = recommended.get("captain") or {}
    starting_xi = recommended.get("starting_xi", [])
    captain_id = integer(captain.get("player_id"))
    captain_points = points.get(captain_id, number(captain.get("gameweek_1_expected_points")))
    xi_max = max(
        (
            points.get(
                integer(row.get("player_id")),
                number(row.get("gameweek_1_expected_points")),
            )
            for row in starting_xi
        ),
        default=0,
    )
    captain_passed = (
        captain_id in {integer(row.get("player_id")) for row in starting_xi}
        and captain_points >= xi_max - 0.001
        and captain_points >= 4
    )
    checks["captaincy_sanity"] = _check(
        captain_passed,
        {
            "captain": captain.get("web_name"),
            "captain_expected_points": round(captain_points, 3),
            "starting_xi_maximum": round(xi_max, 3),
        },
        {"captain_is_xi_maximum": True, "minimum_expected_points": 4},
    )
    if not captain_passed:
        issues.append(
            _issue(
                "captaincy_sanity_failed",
                "The proposed captain does not satisfy the launch captaincy safety checks.",
            )
        )

    checks["six_gameweek_route"] = _check(
        route.get("status") == "ready"
        and len(route.get("horizon_gameweeks", [])) >= 3
        and bool(route.get("recommended_route")),
        {
            "status": route.get("status"),
            "horizon_gameweeks": route.get("horizon_gameweeks", []),
            "recommended_route": bool(route.get("recommended_route")),
        },
        {"status": "ready", "minimum_gameweeks": 3, "recommended_route": True},
    )
    if not checks["six_gameweek_route"]["passed"]:
        issues.append(
            _issue(
                "invalid_initial_transfer_route",
                "The recommended opening squad does not have a complete legal multi-Gameweek route.",
            )
        )

    high_severity = sum(issue["severity"] == "high" for issue in issues)
    return {
        "launch_validation_version": LAUNCH_VALIDATION_VERSION,
        "status": "passed" if not high_severity else "review_required",
        "usable_for_selection": not high_severity,
        "checks": checks,
        "issues": issues,
        "high_severity_issue_count": high_severity,
        "principle": "A launch squad cannot be marked ready while any high-severity mapping, projection, squad, route or captaincy check is unresolved.",
    }
