"""Exact-input control-versus-forced route diagnostic during a full model build.

Run on a disposable CI checkout. Captures the optimiser's *actual* evaluated
inputs in memory, then compares its untouched result to a forced first-week
candidate purchase using identical arguments. No output files are committed.
"""
import json
import inspect
import runpy
import sys
from src import fpl_decisions
from src.diagnostic_forced_route import forced_first_week_route


def run(candidate_id=124):
    original = fpl_decisions.optimise_multi_gameweek_route
    evidence = []
    def capture(*args, **kwargs):
        baseline = original(*args, **kwargs)
        bound = inspect.signature(original).bind(*args, **kwargs)
        values = dict(bound.arguments)
        values['candidate_id'] = candidate_id
        forced = forced_first_week_route(**values)
        a = baseline.get("recommended_route") or {}
        b = forced.get("recommended_route") or {}
        evidence.append({
            "candidate_id": candidate_id,
            "horizon": baseline.get("horizon_gameweeks"),
            "baseline": {
                "discounted_objective": a.get("discounted_objective"),
                "projected_net_points": a.get("projected_net_points"),
                "gameweek_plan": a.get("gameweek_plan"),
            },
            "forced": {
                "discounted_objective": b.get("discounted_objective"),
                "projected_net_points": b.get("projected_net_points"),
                "gameweek_plan": b.get("gameweek_plan"),
            },
            "objective_difference_forced_minus_baseline": round(
                float(b["discounted_objective"]) - float(a["discounted_objective"]), 3
            ) if a and b else None,
            "method": "same production optimiser input args, first-GW candidate constrained",
            "limitations": [
                "Both searches use a bounded beam and are not globally optimal.",
                "This is a controlled route counterfactual, not a causal player-value proof.",
            ],
        })
        return baseline

    fpl_decisions.optimise_multi_gameweek_route = capture
    try:
        sys.argv = ["src.build_fpl_model", "--data-dir", "data"]
        runpy.run_module("src.build_fpl_model", run_name="__main__")
    finally:
        fpl_decisions.optimise_multi_gameweek_route = original
    if not evidence:
        raise RuntimeError("Production optimiser was never invoked")
    print("FORCED_ROUTE_DIAGNOSTIC_JSON_START")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    print("FORCED_ROUTE_DIAGNOSTIC_JSON_END")
    return evidence


if __name__ == "__main__":
    run()
