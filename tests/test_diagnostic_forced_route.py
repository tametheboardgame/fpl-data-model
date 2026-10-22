import unittest
from unittest.mock import patch

from src import fpl_multiweek
from src.diagnostic_forced_route import forced_first_week_route


class ForcedRouteTests(unittest.TestCase):
    def test_forced_candidate_only_in_first_search_step(self):
        calls = []
        def fake_options(state, player_by_id, candidate_ids, remaining_points, max_transfers=2):
            calls.append(list(candidate_ids.get("Midfielder", [])))
            return [
                ((1,), {}, 0, []),
                ((2,), {}, 0, [{"buy_player_id": 124}]),
            ]
        def fake_optimiser(*args, **kwargs):
            state = object()
            opts = fpl_multiweek.transfer_options(
                state, {124: {"position": "Midfielder"}},
                {"Midfielder": [427]}, {}, 2)
            assert len(opts) == 1
            assert opts[0][3][0]["buy_player_id"] == 124
            later = fpl_multiweek.transfer_options(
                state, {124: {"position": "Midfielder"}},
                {"Midfielder": [427]}, {}, 2)
            assert len(later) == 2
            return {"recommended_route": {"gameweek_plan": [
                {"transfers": [{"buy_player_id": 124}]}]}}
        with patch.object(fpl_multiweek, "transfer_options", fake_options):
            with patch.object(fpl_multiweek, "optimise_multi_gameweek_route", fake_optimiser):
                result = forced_first_week_route([], [], [], 0, 2, 124, 8)
        self.assertEqual(len(calls), 2)
        self.assertIn(124, calls[0])
        self.assertNotIn(124, calls[1])
        self.assertEqual(result["recommended_route"]["gameweek_plan"][0]["transfers"][0]["buy_player_id"], 124)

    def test_missing_forced_candidate_fails_closed(self):
        def fake_options(*args, **kwargs):
            return [((1,), {}, 0, [])]
        def fake_optimiser(*args, **kwargs):
            fpl_multiweek.transfer_options(object(), {124: {"position": "Midfielder"}}, {}, {})
        with patch.object(fpl_multiweek, "transfer_options", fake_options):
            with patch.object(fpl_multiweek, "optimise_multi_gameweek_route", fake_optimiser):
                with self.assertRaises(ValueError):
                    forced_first_week_route([], [], [], 0, 2, 124, 8)


if __name__ == "__main__":
    unittest.main()
