import unittest

from scheduler.expression import build_expression_from_meetings, parse_expression_to_meetings


class ExpressionTests(unittest.TestCase):
    def test_single_meeting(self):
        self.assertEqual(build_expression_from_meetings([(1, 1)]), "1(A)")

    def test_day_range(self):
        self.assertEqual(build_expression_from_meetings([(1, 1), (2, 1)]), "1(A-B)")

    def test_mod_range(self):
        self.assertEqual(build_expression_from_meetings([(3, 1), (3, 2)]), "1-2(C)")

    def test_non_consecutive_mods_are_split(self):
        self.assertEqual(build_expression_from_meetings([(1, 2), (1, 8)]), "2(A) 8(A)")

    def test_complex_example(self):
        expr = build_expression_from_meetings(
            [(1, 9), (2, 9), (4, 9), (1, 10), (2, 10), (4, 10), (3, 12)]
        )
        self.assertEqual(expr, "9-10(A-B,D) 12(C)")

    def test_multiple_tokens(self):
        expr = build_expression_from_meetings([(1, 1), (3, 1), (2, 2), (3, 2)])
        self.assertEqual(expr, "1(A,C) 2(B-C)")

    def test_owner_example_mixed_ranges(self):
        expr = build_expression_from_meetings(
            [(1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (2, 4), (5, 4), (2, 5), (5, 5), (2, 6), (5, 6)]
        )
        self.assertEqual(expr, "2(A-E) 4-6(B,E)")

    def test_ignores_invalid_day_codes(self):
        expr = build_expression_from_meetings([(6, 2), (1, 2), (2, 2), (0, 2)])
        self.assertEqual(expr, "2(A-B)")

    def test_parse_expression_mixed_ranges(self):
        meetings = parse_expression_to_meetings("9-10(A-B,D) 12(C)")
        self.assertIn((1, 9), meetings)
        self.assertIn((2, 10), meetings)
        self.assertIn((4, 10), meetings)
        self.assertIn((3, 12), meetings)


if __name__ == "__main__":
    unittest.main()
