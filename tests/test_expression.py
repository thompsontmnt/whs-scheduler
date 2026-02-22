import unittest

from scheduler.expression import build_expression_from_meetings


class ExpressionTests(unittest.TestCase):
    def test_single_meeting(self):
        self.assertEqual(build_expression_from_meetings([(1, 1)]), "1(A)")

    def test_day_range(self):
        self.assertEqual(build_expression_from_meetings([(1, 1), (2, 1)]), "1(A-B)")

    def test_mod_range(self):
        self.assertEqual(build_expression_from_meetings([(3, 1), (3, 2)]), "1-2(C)")

    def test_multiple_tokens(self):
        expr = build_expression_from_meetings([(1, 1), (3, 1), (2, 2), (3, 2)])
        self.assertEqual(expr, "1(A,C) 2(B-C)")


if __name__ == "__main__":
    unittest.main()
