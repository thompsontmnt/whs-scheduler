"""Convert input files to model objects."""

import csv
from pathlib import Path

from scheduler.models import Course, Request, SectionTemplate, Student


# reqexport.txt columns (0-indexed): Student Name, Student Number, Next Grade, School, Dept, Course #, Course_Name, ...
_REQEXPORT_MIN_COLS = 7
_REQEXPORT_HEADER_FIRST = "Student Name"
_REQEXPORT_REQUEST_TYPE_INDEX = 10


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
    """Build normalized requests from reqexport.

    Rules:
    - keep only rows where Request Type is empty or Primary
    - dedupe by (student_id, class_code), preserving first occurrence
    """
    requests: list[Request] = []
    seen_pairs: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < _REQEXPORT_MIN_COLS:
                continue
            if row[0].strip() == _REQEXPORT_HEADER_FIRST:
                continue
            request_type = ""
            if len(row) > _REQEXPORT_REQUEST_TYPE_INDEX:
                request_type = row[_REQEXPORT_REQUEST_TYPE_INDEX].strip().strip('"').lower()
            if request_type and request_type != "primary":
                continue
            student_id = row[1].strip()
            class_code = row[5].strip()
            pair = (student_id, class_code)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
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


def load_section_templates(path: Path) -> dict[str, list[SectionTemplate]]:
    """Load section template rows from tab-delimited file.

    Expected header columns:
    class_code, expression, section_number, teacher_id, section_id, term_id, school_id, build_id, period

    Optional:
    - date_enrolled, date_left, max_enrollment, room, section_type: additional ScheduleCC import fields
    - day, mod: numeric meeting coordinates used for expression generation
    - tied: tied/untied flag. Defaults to tied.
    """

    def _to_int(raw: str) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    grouped: dict[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, bool], dict[str, object]] = {}
    ungrouped: list[tuple[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, bool], dict[str, object]]] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            class_code = (row.get("class_code") or "").strip()
            if not class_code:
                continue
            expression = (row.get("expression") or "").strip()
            section_number = (row.get("section_number") or "").strip()
            teacher_id = (row.get("teacher_id") or "").strip()
            section_id = (row.get("section_id") or "").strip()
            term_id = (row.get("term_id") or "").strip()
            school_id = (row.get("school_id") or "25").strip()
            build_id = (row.get("build_id") or "").strip()
            period = (row.get("period") or "").strip()
            date_enrolled = (row.get("date_enrolled") or "").strip()
            date_left = (row.get("date_left") or "").strip()
            max_enrollment = (row.get("max_enrollment") or "").strip()
            room = (row.get("room") or "").strip()
            section_type = (row.get("section_type") or "").strip()
            tied_raw = (row.get("tied") or "").strip().lower()
            tied = tied_raw not in {"untied", "false", "0", "n", "no"}

            day = _to_int((row.get("day") or "").strip())
            mod = _to_int((row.get("mod") or "").strip())
            meetings = {(day, mod)} if day > 0 and mod > 0 else set()

            key = (
                class_code,
                section_number,
                teacher_id,
                section_id,
                term_id,
                school_id,
                build_id,
                period,
                date_enrolled,
                date_left,
                max_enrollment,
                room,
                section_type,
                tied,
            )

            if tied:
                if key not in grouped:
                    grouped[key] = {"expression": expression, "meetings": set()}
                if expression and not grouped[key]["expression"]:
                    grouped[key]["expression"] = expression
                grouped_meetings = grouped[key]["meetings"]
                assert isinstance(grouped_meetings, set)
                grouped_meetings.update(meetings)
            else:
                ungrouped.append((key, {"expression": expression, "meetings": meetings}))

    templates: dict[str, list[SectionTemplate]] = {}

    def _append_template(key: tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, bool], value: dict[str, object]) -> None:
        (
            class_code,
            section_number,
            teacher_id,
            section_id,
            term_id,
            school_id,
            build_id,
            period,
            date_enrolled,
            date_left,
            max_enrollment,
            room,
            section_type,
            tied,
        ) = key
        expression = value["expression"] if isinstance(value["expression"], str) else ""
        meetings_value = value["meetings"] if isinstance(value["meetings"], set) else set()
        template = SectionTemplate(
            class_code=class_code,
            expression=expression,
            section_number=section_number,
            teacher_id=teacher_id,
            section_id=section_id,
            term_id=term_id,
            school_id=school_id,
            build_id=build_id,
            period=period,
            date_enrolled=date_enrolled,
            date_left=date_left,
            max_enrollment=max_enrollment,
            room=room,
            section_type=section_type,
            meetings=tuple(sorted(meetings_value)),
            tied=tied,
        )
        templates.setdefault(class_code, []).append(template)

    for key, value in grouped.items():
        _append_template(key, value)
    for key, value in ungrouped:
        _append_template(key, value)

    return templates
