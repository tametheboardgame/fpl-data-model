from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.external_context import load_source_registry, read_context_signals


BASE_URL = "https://api.the-odds-api.com/v4"
SPORT_KEY = "soccer_epl"
DEFAULT_TOTAL_GOALS = 2.85
TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "newcastle united": "newcastle",
    "nottingham forest": "nott'm forest",
    "tottenham hotspur": "spurs",
    "wolverhampton wanderers": "wolves",
}


class OddsApiError(RuntimeError):
    pass


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalise(value: Any) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def normalise_team(value: Any) -> str:
    name = normalise(value)
    return normalise(TEAM_ALIASES.get(name, name))


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _team_name(fixture: dict[str, Any], side: str) -> Any:
    return fixture.get(f"{side}_team_name") or fixture.get(f"{side}_team")


def match_events(
    provider_events: list[dict[str, Any]], fpl_fixtures: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    matched: dict[str, dict[str, Any]] = {}
    for event in provider_events:
        event_id = str(event.get("id") or "")
        kickoff = parse_time(event.get("commence_time"))
        if not event_id or not kickoff:
            continue
        home = normalise_team(event.get("home_team"))
        away = normalise_team(event.get("away_team"))
        candidates = [
            fixture
            for fixture in fpl_fixtures
            if normalise_team(_team_name(fixture, "home")) == home
            and normalise_team(_team_name(fixture, "away")) == away
            and parse_time(fixture.get("kickoff_time"))
            and abs(
                (parse_time(fixture.get("kickoff_time")) - kickoff).total_seconds()
            )
            <= 48 * 3600
        ]
        if len(candidates) == 1:
            matched[event_id] = candidates[0]
    return matched


def _normalised_probabilities(prices: dict[str, float]) -> dict[str, float]:
    implied = {
        name: 1 / price
        for name, price in prices.items()
        if isinstance(price, (int, float)) and price > 1
    }
    total = sum(implied.values())
    return {name: value / total for name, value in implied.items()} if total else {}


def _poisson_cdf(limit: int, rate: float) -> float:
    term = math.exp(-rate)
    cumulative = term
    for value in range(1, limit + 1):
        term *= rate / value
        cumulative += term
    return cumulative


def total_goals_from_over_probability(probability: float, point: float) -> float:
    threshold = math.floor(point)
    target = max(0.01, min(0.99, probability))
    lower, upper = 0.05, 8.0
    for _ in range(60):
        middle = (lower + upper) / 2
        over = 1 - _poisson_cdf(threshold, middle)
        if over < target:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def _score_probabilities(home_rate: float, away_rate: float) -> dict[str, float]:
    home_scores = [math.exp(-home_rate)]
    away_scores = [math.exp(-away_rate)]
    for goals in range(1, 13):
        home_scores.append(home_scores[-1] * home_rate / goals)
        away_scores.append(away_scores[-1] * away_rate / goals)
    home_win = draw = away_win = 0.0
    for home_goals, home_probability in enumerate(home_scores):
        for away_goals, away_probability in enumerate(away_scores):
            probability = home_probability * away_probability
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability
    total = home_win + draw + away_win
    return {
        "home": home_win / total,
        "draw": draw / total,
        "away": away_win / total,
    }


def fit_team_goal_rates(
    outcome_probabilities: dict[str, float], total_goals: float
) -> tuple[float, float]:
    total_goals = max(0.3, min(7.5, total_goals))
    best = (total_goals / 2, total_goals / 2)
    best_error = float("inf")
    for step in range(1, 500):
        home_rate = total_goals * step / 500
        away_rate = total_goals - home_rate
        model = _score_probabilities(home_rate, away_rate)
        error = sum(
            (model[outcome] - outcome_probabilities[outcome]) ** 2
            for outcome in ("home", "draw", "away")
        )
        if error < best_error:
            best_error = error
            best = (home_rate, away_rate)
    return best


def market_consensus(event: dict[str, Any]) -> dict[str, Any] | None:
    home_name = str(event.get("home_team") or "")
    away_name = str(event.get("away_team") or "")
    h2h_rows: list[dict[str, float]] = []
    total_goal_rates: list[float] = []
    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            outcomes = market.get("outcomes", [])
            if market.get("key") == "h2h":
                prices = {str(row.get("name")): row.get("price") for row in outcomes}
                probabilities = _normalised_probabilities(prices)
                draw_name = next(
                    (name for name in probabilities if normalise(name) == "draw"), None
                )
                if home_name in probabilities and away_name in probabilities and draw_name:
                    h2h_rows.append(
                        {
                            "home": probabilities[home_name],
                            "draw": probabilities[draw_name],
                            "away": probabilities[away_name],
                        }
                    )
            if market.get("key") == "totals":
                by_point: dict[float, dict[str, float]] = {}
                for row in outcomes:
                    try:
                        point = float(row.get("point"))
                        price = float(row.get("price"))
                    except (TypeError, ValueError):
                        continue
                    by_point.setdefault(point, {})[normalise(row.get("name"))] = price
                for point, prices in by_point.items():
                    probabilities = _normalised_probabilities(prices)
                    if "over" in probabilities and "under" in probabilities:
                        total_goal_rates.append(
                            total_goals_from_over_probability(probabilities["over"], point)
                        )
    if not h2h_rows:
        return None
    outcomes = {
        outcome: statistics.median(row[outcome] for row in h2h_rows)
        for outcome in ("home", "draw", "away")
    }
    probability_total = sum(outcomes.values())
    outcomes = {key: value / probability_total for key, value in outcomes.items()}
    total_goals = (
        statistics.median(total_goal_rates)
        if total_goal_rates
        else DEFAULT_TOTAL_GOALS
    )
    home_rate, away_rate = fit_team_goal_rates(outcomes, total_goals)
    return {
        "outcome_probabilities": outcomes,
        "home_expected_goals": home_rate,
        "away_expected_goals": away_rate,
        "home_score_probability": 1 - math.exp(-home_rate),
        "away_score_probability": 1 - math.exp(-away_rate),
        "home_clean_sheet_probability": math.exp(-away_rate),
        "away_clean_sheet_probability": math.exp(-home_rate),
        "bookmaker_count": len(h2h_rows),
        "totals_bookmaker_count": len(total_goal_rates),
        "total_goals_source": "bookmaker_totals" if total_goal_rates else "league_prior",
    }


def _signal(
    *, event: dict[str, Any], fixture: dict[str, Any], team_id: int,
    signal_type: str, value: float, observed_at: datetime, confidence: float,
    note: str,
) -> dict[str, Any]:
    event_id = str(event.get("id"))
    stamp = observed_at.replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    kickoff = parse_time(fixture.get("kickoff_time"))
    expires = kickoff + timedelta(hours=4) if kickoff else observed_at + timedelta(days=3)
    return {
        "signal_id": f"odds-api-{signal_type}-{event_id}-{team_id}-{stamp}",
        "observed_at": observed_at.replace(microsecond=0).isoformat(),
        "valid_from": observed_at.replace(microsecond=0).isoformat(),
        "expires_at": expires.replace(microsecond=0).isoformat(),
        "source_id": "odds_api_market",
        "signal_type": signal_type,
        "value": round(value, 6),
        "confidence": round(confidence, 6),
        "team_id": team_id,
        "fixture_id": int(float(fixture.get("fixture_id") or 0)),
        "gameweek": int(float(fixture.get("gameweek") or 0)),
        "source_url": "https://the-odds-api.com/",
        "note": note,
        "status": "active",
    }


def signals_from_event(
    event: dict[str, Any], fixture: dict[str, Any], observed_at: datetime
) -> list[dict[str, Any]]:
    consensus = market_consensus(event)
    if not consensus:
        return []
    home_id = int(float(fixture.get("home_team_id") or 0))
    away_id = int(float(fixture.get("away_team_id") or 0))
    if not home_id or not away_id:
        return []
    bookmaker_count = int(consensus["bookmaker_count"])
    confidence = min(1.0, bookmaker_count / 5)
    note = (
        f"No-vig median of {bookmaker_count} UK bookmaker(s); "
        f"goal total from {consensus['total_goals_source']}."
    )
    fields = (
        (home_id, "match_win_probability", consensus["outcome_probabilities"]["home"]),
        (away_id, "match_win_probability", consensus["outcome_probabilities"]["away"]),
        (home_id, "team_score_probability", consensus["home_score_probability"]),
        (away_id, "team_score_probability", consensus["away_score_probability"]),
        (home_id, "clean_sheet_probability", consensus["home_clean_sheet_probability"]),
        (away_id, "clean_sheet_probability", consensus["away_clean_sheet_probability"]),
        (home_id, "team_expected_goals", consensus["home_expected_goals"]),
        (away_id, "team_expected_goals", consensus["away_expected_goals"]),
    )
    return [
        _signal(
            event=event, fixture=fixture, team_id=team_id, signal_type=signal_type,
            value=value, observed_at=observed_at, confidence=confidence, note=note,
        )
        for team_id, signal_type, value in fields
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def append_signals(path: Path, signals: list[dict[str, Any]], registry_path: Path) -> int:
    registry = load_source_registry(registry_path)
    existing = {str(row["signal_id"]) for row in read_context_signals(path, registry)}
    fresh = [row for row in signals if str(row["signal_id"]) not in existing]
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    read_context_signals(path, registry)
    return len(fresh)


class OddsApiClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.usage: dict[str, int | None] = {
            "requests_remaining": None,
            "requests_used": None,
            "last_request_cost": None,
        }

    def odds(self) -> list[dict[str, Any]]:
        import requests

        response = requests.get(
            f"{BASE_URL}/sports/{SPORT_KEY}/odds/",
            params={
                "apiKey": self.api_key,
                "regions": "uk",
                "markets": "h2h,totals",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
            timeout=30,
        )
        for header, key in (
            ("x-requests-remaining", "requests_remaining"),
            ("x-requests-used", "requests_used"),
            ("x-requests-last", "last_request_cost"),
        ):
            try:
                self.usage[key] = int(response.headers.get(header, ""))
            except (TypeError, ValueError):
                self.usage[key] = None
        try:
            payload = response.json()
        except ValueError as exc:
            raise OddsApiError(f"The Odds API returned non-JSON status {response.status_code}") from exc
        if not response.ok:
            message = payload.get("message") if isinstance(payload, dict) else str(payload)
            raise OddsApiError(f"The Odds API returned {response.status_code}: {message}")
        if not isinstance(payload, list):
            raise OddsApiError("The Odds API response was not a list of events")
        return payload


def sync(
    data_dir: Path, client: OddsApiClient, now: datetime | None = None,
    force_provider_check: bool = False,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    fixtures = read_csv(data_dir / "chatgpt" / "fixtures.csv")
    future_fixtures = [
        row for row in fixtures
        if parse_time(row.get("kickoff_time")) and parse_time(row.get("kickoff_time")) > now
    ]
    status_path = data_dir / "context" / "odds_api_status.json"
    if not future_fixtures and not force_provider_check:
        status = {
            "provider": "The Odds API",
            "status": "waiting_for_fpl_fixtures",
            "generated_at": now.replace(microsecond=0).isoformat(),
            "request_count": 0,
            "request_cost": 0,
            "signals_appended": 0,
            "reason": "No future FPL fixtures are available, so quota was not used.",
        }
        _write_json(status_path, status)
        return status

    events = client.odds()
    _write_json(data_dir / "raw" / "external" / "odds-api" / "latest" / "odds.json", events)
    event_map = match_events(events, future_fixtures)
    signals: list[dict[str, Any]] = []
    marketless_events = 0
    for event in events:
        fixture = event_map.get(str(event.get("id") or ""))
        if not fixture:
            continue
        rows = signals_from_event(event, fixture, now)
        if not rows:
            marketless_events += 1
        signals.extend(rows)
    appended = append_signals(
        data_dir / "context" / "signals.jsonl", signals,
        data_dir / "context" / "sources.json",
    )
    status_name = "ok" if event_map else (
        "waiting_for_fpl_fixtures" if not future_fixtures else "no_matching_events"
    )
    status = {
        "provider": "The Odds API",
        "status": status_name,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "sport_key": SPORT_KEY,
        "regions": ["uk"],
        "markets": ["h2h", "totals"],
        "request_count": 1,
        "request_cost": client.usage.get("last_request_cost"),
        "requests_used": client.usage.get("requests_used"),
        "requests_remaining": client.usage.get("requests_remaining"),
        "provider_events": len(events),
        "future_fpl_fixtures": len(future_fixtures),
        "matched_fixtures": len(event_map),
        "marketless_matched_events": marketless_events,
        "signals_generated": len(signals),
        "signals_appended": appended,
    }
    _write_json(status_path, status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync no-vig Premier League market probabilities from The Odds API"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--force-provider-check", action="store_true")
    args = parser.parse_args()
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ODDS_API_KEY is not configured")
    try:
        status = sync(
            args.data_dir, OddsApiClient(key),
            force_provider_check=args.force_provider_check,
        )
    except Exception as exc:
        status = {
            "provider": "The Odds API",
            "status": "error",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
        _write_json(args.data_dir / "context" / "odds_api_status.json", status)
        print(json.dumps(status, indent=2))
        raise
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
