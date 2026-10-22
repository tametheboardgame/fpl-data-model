"""Read-only production decision challenger audit. No model imports or writes."""
import argparse
import json
from pathlib import Path


def audit(report, decisions, candidate="Groß", chosen="Mbeumo"):
    if report["target_gameweek"] != decisions["target_gameweek"]:
        raise ValueError("Gameweek mismatch")
    if decisions["team_id"] != 39395:
        raise ValueError("Unexpected team ID")
    policy = report.get("model_governance", report.get("model_policy", {}))
    if report.get("recommendation", {}).get("selection_source") not in (None, "registered_team"):
        raise ValueError("Registered team not verified in production report")
    transfers = report["recommendation"]["transfers"]
    shortlist = decisions["transfer_shortlist"]
    matches = [entry for entry in shortlist if entry["buy"]["web_name"].casefold() == candidate.casefold()]
    if not matches:
        raise ValueError(f"{candidate} absent from transfer shortlist; cannot claim considered")
    chosen_matches = [entry for entry in shortlist if entry["buy"]["web_name"].casefold() == chosen.casefold()]
    plan = decisions["multi_gameweek_plan"]
    routes = [plan.get("recommended_route", {})] + list(plan.get("alternative_routes", []))
    candidate_routes = [
        {"route_index": i, "projected_net_points": route.get("projected_net_points"),
         "discounted_objective": route.get("discounted_objective"),
         "decision_adjusted_gain_vs_hold": route.get("decision_adjusted_gain_vs_hold"),
         "first_week_transfers": route.get("gameweek_plan", [{}])[0].get("transfers", [])}
        for i, route in enumerate(routes)
        if any(t.get("buy", "").casefold() == candidate.casefold()
               for gw in route.get("gameweek_plan", [])
               for t in gw.get("transfers", []))
    ]
    winning = plan.get("recommended_route", {})
    candidate_shortlist_score = matches[0].get("three_gameweek_gain")
    chosen_shortlist_score = chosen_matches[0].get("three_gameweek_gain") if chosen_matches else None
    return {
        "scope": "read_only_diagnostic_not_counterfactual_optimisation",
        "generated_at": decisions["generated_at"],
        "gameweek": decisions["target_gameweek"],
        "team_id": decisions["team_id"],
        "production_transfers": transfers,
        "candidate_shortlist": matches,
        "candidate_three_gameweek_gain": candidate_shortlist_score,
        "chosen_three_gameweek_gain_if_listed": chosen_shortlist_score,
        "published_route_count": len(routes),
        "published_candidate_routes": candidate_routes,
        "published_winner_six_gameweek_net_points": winning.get("projected_net_points"),
        "published_winner_six_gameweek_discounted_objective": winning.get("discounted_objective"),
        "candidate_forced_optimisation_performed": False,
        "chosen_shortlist": chosen_matches,
        "recommended_route": plan.get("recommended_route"),
        "alternative_routes": plan.get("alternative_routes"),
        "policy_observed_in_report": policy,
        "limitations": [
            "Shortlist marginal three-GW scores are not comparable to six-GW route utility.",
            "Existing alternative routes are not a forced Groß counterfactual.",
            "Re-run route optimiser with candidate constraints before claiming an optimality gap.",
            "Independently verify actual registered FPL squad and team news before action.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("data/chatgpt/gameweek_report.json"))
    parser.add_argument("--decisions", type=Path, default=Path("data/chatgpt/fpl_decisions.json"))
    parser.add_argument("--candidate", default="Groß")
    parser.add_argument("--chosen", default="Mbeumo")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    print(json.dumps(audit(report, decisions, args.candidate, args.chosen), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
