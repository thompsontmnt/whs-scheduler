"""Convert input files to model objects."""

import csv
from pathlib import Path

from scheduler.expression import parse_expression_to_meetings
from scheduler.models import Course, Request, SectionOffering, SectionTemplate, Student


# reqexport.txt columns (0-indexed): Student Name, Student Number, Next Grade, School, Dept, Course #, Course_Name, ...
_REQEXPORT_MIN_COLS = 7
_REQEXPORT_HEADER_FIRST = "Student Name"
_REQEXPORT_REQUEST_TYPE_INDEX = 10

# Request families where duplicate weekday variants should be interpreted as
# "keep one request in the current scheduling run and defer the duplicate to S2".
# This mirrors the PowerSchool lunch behavior closely enough for this scheduler
# until the request export carries explicit semester designation for lunch rows.
_AUTO_SEMESTER_BASE_CODES = {"2912"}


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


def load_requests_export(path: Path) -> list[Request]:
    """Load PowerSchool ScheduleRequests.export format (tab-delimited)."""
    requests: list[Request] = []
    seen: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="	")
        for row in reader:
            student_number = (row.get("Student_Number") or "").strip()
            course_number = (row.get("CourseNumber") or "").strip()
            if not student_number or not course_number:
                continue
            pair = (student_number, course_number)
            if pair in seen:
                continue
            seen.add(pair)
            requests.append(Request(student_id=student_number, class_code=course_number))
    return requests


def _check_duplicate_headers(path: Path, delimiter: str = "\t") -> None:
    """Warn if the file has duplicate column names.

    csv.DictReader silently uses the *last* value for any duplicate key, which
    can cause subtle bugs when a column appears twice (e.g. MaxEnrollment in the
    PowerSchool section-offerings export).  Calling this before opening the
    DictReader surfaces the issue at load time so it is never silently ignored.
    """
    import sys
    with path.open(newline="", encoding="utf-8") as f:
        header_line = f.readline()
    headers = header_line.rstrip("\r\n").split(delimiter)
    seen: set[str] = set()
    dupes: list[str] = []
    for h in headers:
        if h in seen and h not in dupes:
            dupes.append(h)
        seen.add(h)
    if dupes:
        print(
            f"WARNING ({path.name}): duplicate column name(s) {dupes}. "
            "csv.DictReader will use the LAST occurrence of each — earlier "
            "columns with the same name are invisible to the parser. "
            "Consider deduplicating the export before re-running.",
            file=sys.stderr,
        )


def load_section_offerings(path: Path) -> dict[str, list[SectionOffering]]:
    """Load section offerings from schedule export (tab-delimited)."""
    _check_duplicate_headers(path)
    offerings: dict[str, list[SectionOffering]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="	")
        for row in reader:
            class_code = (row.get("Course_Number") or "").strip()
            if not class_code:
                continue
            section_number = (row.get("Section_Number") or "").strip()
            teacher_id = (row.get("Teacher") or "").strip()
            term_id = (row.get("TermID") or "").strip()
            expression = (row.get("Expression") or "").strip().strip('"')
            room = (row.get("Room") or "").strip()
            section_type = (row.get("GradebookType") or "").strip()
            tied_raw = (row.get("Tied") or "").strip()
            tied = tied_raw not in {"0", "false", "False", "N", "n", "no", "No"}
            school_id = (row.get("SchoolID") or "25").strip() or "25"
            build_id = (row.get("BuildID") or "").strip()
            max_raw = (row.get("MaxEnrollment") or "").strip()
            phase_raw = (row.get("Phase") or "0").strip()
            section_id = (row.get("SectionID") or row.get("Section ID") or f"{term_id}-{class_code}-{section_number}").strip()
            try:
                max_enrollment = int(max_raw) if max_raw else 0
            except ValueError:
                max_enrollment = 0
            try:
                phase = int(phase_raw) if phase_raw else 0
            except ValueError:
                phase = 0

            offerings.setdefault(class_code, []).append(
                SectionOffering(
                    class_code=class_code,
                    section_number=section_number,
                    teacher_id=teacher_id,
                    section_id=section_id,
                    term_id=term_id,
                    expression=expression,
                    meetings=parse_expression_to_meetings(expression),
                    room=room,
                    max_enrollment=max_enrollment,
                    school_id=school_id,
                    build_id=build_id,
                    section_type=section_type,
                    tied=tied,
                    phase=phase,
                )
            )

    for class_code, rows in offerings.items():
        offerings[class_code] = sorted(
            rows,
            key=lambda o: (o.phase, o.section_number, o.teacher_id, o.section_id),
        )
    return offerings


def load_students_from_requests_export(path: Path) -> dict[str, Student]:
    """Build minimal students map from ScheduleRequests.export Student_Number values."""
    students: dict[str, Student] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="	")
        for row in reader:
            student_number = (row.get("Student_Number") or "").strip()
            if not student_number or student_number in students:
                continue
            students[student_number] = Student(
                student_id=student_number,
                name="",
                gender="",
                grad_year=0,
            )
    return students


def load_courses_from_section_offerings(path: Path) -> dict[str, Course]:
    """Build minimal course catalog from section offerings Course_Number values."""
    courses: dict[str, Course] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="	")
        for row in reader:
            class_code = (row.get("Course_Number") or "").strip()
            if not class_code:
                continue
            if class_code not in courses:
                courses[class_code] = Course(
                    class_code=class_code,
                    dept_code="",
                    name=class_code,
                    duration_flag="S1",
                    semester_flag="S1",
                )
    return courses


def load_courses_from_requests_export(path: Path) -> dict[str, Course]:
    """Build minimal course catalog from ScheduleRequests.export CourseNumber values."""
    courses: dict[str, Course] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            class_code = (row.get("CourseNumber") or "").strip()
            if not class_code or class_code in courses:
                continue
            courses[class_code] = Course(
                class_code=class_code,
                dept_code="",
                name=class_code,
                duration_flag="S1",
                semester_flag="S1",
            )
    return courses


def reconcile_requests_to_offerings(
    requests: list[Request],
    offerings: dict[str, list[SectionOffering]],
) -> tuple[list[Request], list[tuple[str, str, str, str]]]:
    """Normalize requests for section-offering scheduling.

    - Drop requests for class codes with no offerings.
    - Collapse weekday variant families (e.g., 2912, 2912Tu, 2912W, 2912Th, 2912F)
      to at most one request per student/base family.
    - For lunch-family base codes in _AUTO_SEMESTER_BASE_CODES, interpret dropped
      duplicates as automatically deferred to semester 2.
    Returns (normalized_requests, dropped_rows).

    dropped_rows tuple format: (student_id, class_code, reason, detail)
    """
    import re

    offered_codes = set(offerings.keys())
    family_re = re.compile(r"^(\d+)(Tu|Th|W|F)?$")
    priority = {"": 0, "Tu": 1, "W": 2, "Th": 3, "F": 4}

    filtered: list[Request] = []
    dropped_rows: list[tuple[str, str, str, str]] = []
    for request in requests:
        if request.class_code not in offered_codes:
            dropped_rows.append((request.student_id, request.class_code, "no_section_offering", ""))
            continue
        filtered.append(request)

    by_student_family: dict[tuple[str, str], Request] = {}
    passthrough: list[Request] = []

    for request in filtered:
        match = family_re.match(request.class_code)
        if not match:
            passthrough.append(request)
            continue
        base, suffix = match.groups()
        suffix = suffix or ""
        key = (request.student_id, base)
        existing = by_student_family.get(key)
        if existing is None:
            by_student_family[key] = request
            continue
        existing_match = family_re.match(existing.class_code)
        existing_suffix = existing_match.group(2) if existing_match else ""
        existing_suffix = existing_suffix or ""
        if priority.get(suffix, 99) < priority.get(existing_suffix, 99):
            reason = "lunch_auto_semester2" if base in _AUTO_SEMESTER_BASE_CODES else "weekday_variant_collapsed"
            dropped_rows.append((existing.student_id, existing.class_code, reason, request.class_code))
            by_student_family[key] = request
        else:
            reason = "lunch_auto_semester2" if base in _AUTO_SEMESTER_BASE_CODES else "weekday_variant_collapsed"
            dropped_rows.append((request.student_id, request.class_code, reason, existing.class_code))

    normalized = passthrough + list(by_student_family.values())
    normalized_sorted = sorted(normalized, key=lambda r: (r.student_id, r.class_code))
    dropped_sorted = sorted(dropped_rows, key=lambda row: (row[0], row[1], row[2], row[3]))
    return (normalized_sorted, dropped_sorted)
