import tempfile
import unittest
from pathlib import Path

from scheduler.parsers import load_section_templates
from scheduler.reports import write_schedulecc_csv
from scheduler.models import Assignment


class SectionTemplateTests(unittest.TestCase):
    def test_group_rows_and_build_expression(self):
        content = (
            "class_code\texpression\tsection_number\tteacher_id\tsection_id\tterm_id\tschool_id\tbuild_id\tperiod\tday\tmod\n"
            "1012\t\t1\t20134\t305469\t3501\t25\t3558\t\t1\t1\n"
            "1012\t\t1\t20134\t305469\t3501\t25\t3558\t\t2\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "section_templates.txt"
            out = Path(d) / "schedulecc.csv"
            p.write_text(content, encoding="utf-8")
            templates = load_section_templates(p)
            self.assertIn("1012", templates)
            self.assertEqual(len(templates["1012"]), 1)
            self.assertEqual(templates["1012"][0].meetings, ((1, 1), (2, 1)))

            write_schedulecc_csv(out, [Assignment(student_id="123", class_code="1012")], templates)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertIn('"1(A-B)"', lines[1])


if __name__ == "__main__":
    unittest.main()
