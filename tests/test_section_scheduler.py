import tempfile
import unittest
from pathlib import Path

from scheduler.engine import Scheduler, _invalid_offerings
from scheduler.models import Course, Request, Student
from scheduler.parsers import (
    load_courses_from_requests_export,
    load_courses_from_section_offerings,
    load_section_offerings,
    load_students_from_requests_export,
    reconcile_requests_to_offerings,
)
from scheduler.reports import write_schedulecc_csv_from_sections


class SectionSchedulerTests(unittest.TestCase):

    def test_build_students_and_courses_from_new_exports(self):
        requests_text = (
            "StudentID\tStudent_Number\tCourseNumber\tYearID\n"
            "1\t90001\tMATH1\t3500\n"
            "2\t90002\tENG1\t3500\n"
        )
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\tMATH1\t100\t\"1(A-B)\"\t1\t101\t1\t1\t1\n"
            "3500\tENG1\t200\t\"2(C-D)\"\t1\t201\t1\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            req = Path(d) / "requests.txt"
            off = Path(d) / "offerings.txt"
            req.write_text(requests_text, encoding="utf-8")
            off.write_text(offerings_text, encoding="utf-8")

            students = load_students_from_requests_export(req)
            courses = load_courses_from_section_offerings(off)
            request_courses = load_courses_from_requests_export(req)

            self.assertEqual(sorted(students.keys()), ["90001", "90002"])
            self.assertIn("MATH1", courses)
            self.assertIn("ENG1", courses)
            self.assertEqual(sorted(request_courses.keys()), ["ENG1", "MATH1"])

    def test_reconcile_requests_drops_missing_and_variant_duplicates(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\t5000\t100\t\"1(A)\"\t1\t101\t10\t1\t1\n"
            "3500\t5000Tu\t101\t\"2(A)\"\t1\t101\t10\t1\t1\n"
            "3500\t1001\t200\t\"2(B)\"\t1\t102\t10\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)
            requests = [
                Request("1", "5000Tu"),
                Request("1", "5000"),
                Request("1", "9999"),
                Request("1", "1001"),
            ]
            normalized, dropped_rows = reconcile_requests_to_offerings(requests, offerings)
            self.assertEqual(len(dropped_rows), 2)
            self.assertEqual([(r.student_id, r.class_code) for r in normalized], [("1", "1001"), ("1", "5000")])
            self.assertEqual({row[2] for row in dropped_rows}, {"no_section_offering", "weekday_variant_collapsed"})


    def test_reconcile_lunch_family_marks_auto_semester2(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\t2912\t100\t\"1(A)\"\t1\t101\t10\t1\t1\n"
            "3500\t2912Tu\t100\t\"1(B)\"\t1\t101\t10\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)
            requests = [Request("1", "2912"), Request("1", "2912Tu")]
            normalized, dropped_rows = reconcile_requests_to_offerings(requests, offerings)
            self.assertEqual(len(normalized), 1)
            self.assertEqual(normalized[0].class_code, "2912")
            self.assertEqual(len(dropped_rows), 1)
            self.assertEqual(dropped_rows[0][2], "lunch_auto_semester2")

    def test_load_offerings_and_schedule_with_overlap_and_capacity(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\tMATH1\t100\t\"1(A-B)\"\t1\t101\t1\t1\t1\n"
            "3500\tENG1\t200\t\"1(A-B)\"\t1\t201\t5\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)

            students = {
                "1": Student("1", "One", "", 2026),
                "2": Student("2", "Two", "", 2026),
            }
            courses = {
                "MATH1": Course("MATH1", "M", "Math", "S1", "S1"),
                "ENG1": Course("ENG1", "E", "Eng", "S1", "S1"),
            }
            requests = [
                Request("1", "MATH1"),
                Request("1", "ENG1"),
                Request("2", "MATH1"),
            ]

            scheduler = Scheduler(capacity_by_class={})
            assignments, conflicts = scheduler.schedule_sections(students, requests, courses, offerings)

            self.assertEqual(len(assignments), 2)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].reason, "No available non-conflicting section")

    def test_invalid_offerings_do_not_block_teacher_only_or_room_only_overlap(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\tTARGET1\t100\t\"1(A)\"\t1\t101\t10\t1\t1\n"
            "3500\tOTHER1\t100\t\"1(A)\"\t1\t202\t10\t1\t1\n"
            "3500\tTARGET2\t200\t\"2(A)\"\t1\t303\t10\t1\t1\n"
            "3500\tOTHER2\t201\t\"2(A)\"\t1\t303\t10\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)

            blocked = _invalid_offerings(offerings)
            self.assertEqual(blocked, set())

            students = {"1": Student("1", "One", "", 2026)}
            courses = {
                "TARGET1": Course("TARGET1", "D", "Target 1", "S1", "S1"),
                "TARGET2": Course("TARGET2", "D", "Target 2", "S1", "S1"),
            }
            requests = [Request("1", "TARGET1"), Request("1", "TARGET2")]

            scheduler = Scheduler(capacity_by_class={})
            assignments, conflicts = scheduler.schedule_sections(students, requests, courses, offerings)

            self.assertEqual(len(assignments), 2)
            self.assertEqual(len(conflicts), 0)

    def test_invalid_offerings_block_same_teacher_same_room_overlap(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\tTARGET1\t100\t\"1(A)\"\t1\t101\t10\t1\t1\n"
            "3500\tOTHER1\t100\t\"1(A)\"\t1\t101\t10\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)

            blocked = _invalid_offerings(offerings)
            self.assertEqual(
                blocked,
                {"3500-OTHER1-1", "3500-TARGET1-1"},
            )

    def test_schedulecc_generated_from_section_assignments(self):
        offerings_text = (
            "TermID\tCourse_Number\tTeacher\tExpression\tSection_Number\tRoom\tMaxEnrollment\tTied\tPhase\n"
            "3500\tMATH1\t100\t\"2(B-E)\"\t1\t101\t5\t1\t1\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "offerings.txt"
            out = Path(d) / "schedulecc.csv"
            path.write_text(offerings_text, encoding="utf-8")
            offerings = load_section_offerings(path)

            students = {"1": Student("1", "One", "", 2026)}
            courses = {"MATH1": Course("MATH1", "M", "Math", "S1", "S1")}
            requests = [Request("1", "MATH1")]

            scheduler = Scheduler(capacity_by_class={})
            assignments, conflicts = scheduler.schedule_sections(students, requests, courses, offerings)
            self.assertEqual(len(conflicts), 0)

            write_schedulecc_csv_from_sections(out, assignments, offerings)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertIn('"SCHEDULECC.Expression"', lines[0])
            self.assertIn('"2(B-E)"', lines[1])


if __name__ == "__main__":
    unittest.main()
