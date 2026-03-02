import unittest

from scheduler.expression import build_expression_from_meetings


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


if __name__ == "__main__":
    unittest.main()
