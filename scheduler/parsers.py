"""Convert input files to model objects."""

import csv
from pathlib import Path

from scheduler.models import Course, Request, Student


# reqexport.txt columns (0-indexed): Student Name, Student Number, Next Grade, School, Dept, Course #, Course_Name, ...
_REQEXPORT_MIN_COLS = 7
_REQEXPORT_HEADER_FIRST = "Student Name"


def _infer_semester_from_course_name(course_name: str) -> tuple[str, str]:
    """Infer (duration_flag, semester_flag) from course name. reqexport has no F1 field:
    - ' S1' in name → semester 1 only → (S1, S1)
    - ' S2' in name → semester 2 only → (S2, S2)
    - no S1/S2 reference (e.g. Lunch, Construction) → full year, both semesters → (F1, S1) for engine."""
    name_upper = course_name.upper()
    if " S1" in name_upper and " S2" not in name_upper:
        return ("S1", "S1")
    if " S2" in name_upper and " S1" not in name_upper:
        return ("S2", "S2")
    # No S1/S2 in name → full-year course (Lunch, etc.). Engine uses F1 = both semesters.
    return ("F1", "S1")


def load_students(path: Path) -> dict[str, Student]:
    """Load students from tab-delimited file. Returns dict keyed by student_id."""
    students: dict[str, Student] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 7:
                continue
            name = row[0].strip()
            student_id = row[1].strip()
            gender = row[5].strip()
            grad_year = int(row[6].strip())
            students[student_id] = Student(
                student_id=student_id,
                name=name,
                gender=gender,
                grad_year=grad_year,
            )
    return students


def load_requests(path: Path) -> list[Request]:
    """Load course requests from tab-delimited file."""
    requests: list[Request] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 2:
                continue
            student_id = row[0].strip()
            class_code = row[1].strip()
            requests.append(Request(student_id=student_id, class_code=class_code))
    return requests


def load_courses(path: Path) -> dict[str, Course]:
    """Load course metadata from PRIOR.TXT. Returns dict keyed by class_code."""
    courses: dict[str, Course] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 5:
                continue
            class_code = row[0].strip()
            dept_code = row[1].strip()
            name = row[2].strip()
            duration_flag = row[3].strip()
            semester_flag = row[4].strip()
            courses[class_code] = Course(
                class_code=class_code,
                dept_code=dept_code,
                name=name,
                duration_flag=duration_flag,
                semester_flag=semester_flag,
            )
    return courses


# --- reqexport.txt format (tab-delimited, header row) ---


def load_students_from_reqexport(path: Path) -> dict[str, Student]:
    """Build students from reqexport: unique by Student Number. grad_year from Next Grade (9->2029, 12->2026). No gender."""
    students: dict[str, Student] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < _REQEXPORT_MIN_COLS:
                continue
            if row[0].strip() == _REQEXPORT_HEADER_FIRST:
                continue
            name = row[0].strip().strip('"')
            student_id = row[1].strip()
            next_grade = int(row[2].strip())
            grad_year = 2026 + (12 - next_grade)
            if student_id not in students:
                students[student_id] = Student(
                    student_id=student_id,
                    name=name,
                    gender="",
                    grad_year=grad_year,
                )
    return students


def load_requests_from_reqexport(path: Path) -> list[Request]:
    """Build requests from reqexport: one Request per row (Student Number, Course #). Skips header."""
    requests: list[Request] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < _REQEXPORT_MIN_COLS:
                continue
            if row[0].strip() == _REQEXPORT_HEADER_FIRST:
                continue
            student_id = row[1].strip()
            class_code = row[5].strip()
            requests.append(Request(student_id=student_id, class_code=class_code))
    return requests


def load_courses_from_reqexport(path: Path) -> dict[str, Course]:
    """Build course catalog from reqexport: unique by Course # (class_code). Dept, Course_Name; duration/semester inferred from name."""
    courses: dict[str, Course] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < _REQEXPORT_MIN_COLS:
                continue
            if row[0].strip() == _REQEXPORT_HEADER_FIRST:
                continue
            class_code = row[5].strip()
            dept_code = row[4].strip()
            name = row[6].strip()
            duration_flag, semester_flag = _infer_semester_from_course_name(name)
            courses[class_code] = Course(
                class_code=class_code,
                dept_code=dept_code,
                name=name,
                duration_flag=duration_flag,
                semester_flag=semester_flag,
            )
    return courses
