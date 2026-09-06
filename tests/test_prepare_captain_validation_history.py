from __future__ import annotations

import unittest

from src.prepare_captain_validation_history import (
    parse_fixture_teams,
    parse_position_metadata,
    truthy,
)


class CaptainValidationHistoryPreparationTests(unittest.TestCase):
    def test_parser_retains_only_id_to_position_mapping(self) -> None:
        text = (
            "id,element_type,now_cost,selected_by_percent,team,total_points\n"
            "1,1,55,14.2,3,120\n"
            "2,2,50,25.0,4,130\n"
            "3,3,80,40.0,5,170\n"
            "4,4,95,35.0,6,190\n"
            "5,,45,1.0,7,20\n"
        )
        self.assertEqual(
            parse_position_metadata(text),
            {"1": "GK", "2": "DEF", "3": "MID", "4": "FWD"},
        )

    def test_unknown_element_type_is_ignored(self) -> None:
        text = "id,element_type\n10,5\n11,2\n"
        self.assertEqual(parse_position_metadata(text), {"11": "DEF"})

    def test_fixture_parser_retains_only_structural_team_ids(self) -> None:
        text = (
            "id,team_h,team_a,team_h_score,team_a_score,finished,stats\n"
            "101,3,7,4,0,True,result payload\n"
            "102,9,2,1,1,True,other result\n"
            ",5,6,0,0,False,ignored\n"
        )
        self.assertEqual(
            parse_fixture_teams(text),
            {"101": ("3", "7"), "102": ("9", "2")},
        )

    def test_truthy_handles_archived_was_home_values(self) -> None:
        for value in (True, 1, "1", "true", "True", "yes"):
            self.assertTrue(truthy(value))
        for value in (False, 0, "0", "false", "", None):
            self.assertFalse(truthy(value))


if __name__ == "__main__":
    unittest.main()
