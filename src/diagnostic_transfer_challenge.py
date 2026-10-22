"""Read-only production decision challenger audit. No model imports or writes."""
import argparse
import json
from pathlib import Path


def audit(report, decisions, candidate="Groß", chosen="Mbeumo"):
    assert report["target_gameweek"] == decisions["target_gameweek"]
    assert decisions["team_id"] == 39395
    policy = report.get("model_governance", report.get("model_policy", {}))
    transfers = report["recommendation"]["transfers"]
    shortlist = decisions["transfer_shortlist"]
    matches = [entry for entry in shortlist if entry["buy"]["web_name"].casefold() == candidate.casefold()]
    if not matches:
        raise ValueError(f"{candidate} absent from transfer shortlist; cannot claim considered")
    chosen_matches = [entry for entry in shortlist if entry["buy"]["web_name"].casefold() == chosen.casefold()]
    plan = decisions["multi_gameweek_plan"]
    return {
        "scope": "read_only_diagnostic_not_counterfactual_optimisation",
        "generated_at": decisions["generated_at"],
        "gameweek": decisions["target_gameweek"],
        "team_id": decisions["team_id"],
        "production_transfers": transfers,
        "candidate_shortlist": matches,
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
