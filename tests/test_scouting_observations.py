from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.scouting_observations import (
    append_observation,
    qualitative_adjustment,
    read_observations,
    validate_observation,
)


class ScoutingObservationTests(unittest.TestCase):
    def observation(self) -> dict:
        return {
            "observation_id": "obs-1",
            "observed_at": "2026-08-01T17:00:00+00:00",
            "recorded_at": "2026-08-01T18:00:00+00:00",
            "observer": "David",
            "player_id": 10,
            "player_name": "Example",
            "raw_note": "Looked sharp, played high and was repeatedly found in the box.",
            "attacking_role": 2,
            "movement_sharpness": 2,
            "fitness_energy": 1,
            "minutes_security": 1,
            "set_piece_role": 0,
            "team_reliance": 1,
            "tactical_fit": 1,
            "confidence": 0.8,
            "expires_at": "2026-08-20T23:59:00+00:00",
            "status": "active",
        }

    def test_validates_and_round_trips_jsonl(self) -> None:
        self.assertEqual(validate_observation(self.observation()), [])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observations.jsonl"
            append_observation(path, self.observation())
            rows = read_observations(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_note"], self.observation()["raw_note"])

    def test_adjustment_is_bounded_and_expires(self) -> None:
        player = {"player_id": 10, "player_code": 10010}
        active = qualitative_adjustment(
            [self.observation()], player, "2026-08-08T15:00:00+00:00"
        )
        expired = qualitative_adjustment(
            [self.observation()], player, "2026-08-25T15:00:00+00:00"
        )
        self.assertEqual(active["observation_count"], 1)
        self.assertGreater(active["attack_multiplier"], 1)
        self.assertLessEqual(active["attack_multiplier"], 1.2)
        self.assertLessEqual(active["minutes_delta"], 12)
        self.assertEqual(expired["observation_count"], 0)

    def test_rejects_retroactive_future_observation(self) -> None:
        player = {"player_id": 10, "player_code": 10010}
        adjustment = qualitative_adjustment(
            [self.observation()], player, "2026-07-31T15:00:00+00:00"
        )
        self.assertEqual(adjustment["observation_count"], 0)

    def test_append_only_retraction_removes_old_signal(self) -> None:
        retraction = {
            **self.observation(),
            "observation_id": "retract-1",
            "status": "retracted",
            "retracts_observation_id": "obs-1",
            "raw_note": "Retracted after reviewing the player identity.",
        }
        adjustment = qualitative_adjustment(
            [self.observation(), retraction],
            {"player_id": 10, "player_code": 10010},
            "2026-08-08T15:00:00+00:00",
        )
        self.assertEqual(adjustment["observation_count"], 0)

    def test_late_recording_cannot_enter_an_earlier_forecast(self) -> None:
        late = {
            **self.observation(),
            "recorded_at": "2026-08-10T18:00:00+00:00",
        }
        adjustment = qualitative_adjustment(
            [late],
            {"player_id": 10, "player_code": 10010},
            "2026-08-08T15:00:00+00:00",
        )
        self.assertEqual(adjustment["observation_count"], 0)


if __name__ == "__main__":
    unittest.main()
