"""Output formatting (CSV generation)."""

import csv
import io
from pathlib import Path

from scheduler.expression import build_expression_from_meetings
from scheduler.models import Assignment, Conflict, Course, SectionAssignment, SectionOffering, SectionTemplate, Student


def _semester_display(course: Course) -> str:
    """Single string for semester column: S1, S2, or S1,S2 for full year."""
    if course.duration_flag == "F1":
        return "S1,S2"
    return course.semester_flag


def write_assignments_csv(
    path: Path,
    assignments: list[Assignment],
    students: dict[str, Student],
    courses: dict[str, Course],
) -> None:
    """Write assignments.csv with columns: student_id, student_name, class_code, course_name, semester."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["student_id", "student_name", "class_code", "course_name", "semester"]
        )
        for a in assignments:
            student = students.get(a.student_id)
            course = courses.get(a.class_code)
            student_name = student.name if student else ""
            course_name = course.name if course else ""
            semester = _semester_display(course) if course else ""
            writer.writerow(
                [a.student_id, student_name, a.class_code, course_name, semester]
            )


def write_conflicts_csv(
    path: Path,
    conflicts: list[Conflict],
    students: dict[str, Student],
) -> None:
    """Write conflicts.csv with columns: student_id, student_name, class_code, reason."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "student_name", "class_code", "reason"])
        for c in conflicts:
            student = students.get(c.student_id)
            student_name = student.name if student else ""
            writer.writerow([c.student_id, student_name, c.class_code, c.reason])




def write_dropped_by_reason_csv(
    path: Path,
    dropped_rows: list[tuple[str, str, str, str]],
    students: dict[str, Student],
) -> None:
    """Write dropped_by_reason.csv for reconciled-away requests."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "student_name", "class_code", "reason", "detail"])
        for student_id, class_code, reason, detail in dropped_rows:
            student = students.get(student_id)
            student_name = student.name if student else ""
            writer.writerow([student_id, student_name, class_code, reason, detail])

def assignments_csv_string(
    assignments: list[Assignment],
    students: dict[str, Student],
    courses: dict[str, Course],
) -> str:
    """Return assignments CSV as a string (for API/download)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["student_id", "student_name", "class_code", "course_name", "semester"]
    )
    for a in assignments:
        student = students.get(a.student_id)
        course = courses.get(a.class_code)
        student_name = student.name if student else ""
        course_name = course.name if course else ""
        semester = _semester_display(course) if course else ""
        writer.writerow([a.student_id, student_name, a.class_code, course_name, semester])
    return buf.getvalue()


def conflicts_csv_string(
    conflicts: list[Conflict],
    students: dict[str, Student],
) -> str:
    """Return conflicts CSV as a string (for API/download)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id", "student_name", "class_code", "reason"])
    for c in conflicts:
        student = students.get(c.student_id)
        student_name = student.name if student else ""
        writer.writerow([c.student_id, student_name, c.class_code, c.reason])
    return buf.getvalue()


def write_schedulecc_csv(
    path: Path,
    assignments: list[Assignment],
    section_templates: dict[str, list[SectionTemplate]],
    starting_dcid: int = 1,
) -> None:
    """Write PowerSchool-style ScheduleCC export from assignments and section templates."""
    headers = [
        "SCHEDULECC.dcid",
        "SCHEDULECC.BuildID",
        "SCHEDULECC.Course_Number",
        "SCHEDULECC.DateEnrolled",
        "SCHEDULECC.DateLeft",
        "SCHEDULECC.Expression",
        "SCHEDULECC.Period",
        "SCHEDULECC.SchoolID",
        "SCHEDULECC.Section_Number",
        "SCHEDULECC.SectionType",
        "SCHEDULECC.TermID",
        "SCHEDULECC.StudentID",
        "SCHEDULECC.SectionID",
        "SCHEDULECC.TeacherID",
        "SCHEDULECC.MaxEnrollment",
        "SCHEDULECC.Room",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        dcid = starting_dcid
        usage_by_class: dict[str, int] = {}
        for assignment in assignments:
            templates = section_templates.get(assignment.class_code)
            if not templates:
                continue
            index = usage_by_class.get(assignment.class_code, 0)
            template = templates[index % len(templates)]
            usage_by_class[assignment.class_code] = index + 1
            writer.writerow(
                [
                    str(dcid),
                    template.build_id,
                    assignment.class_code,
                    template.date_enrolled,
                    template.date_left,
                    template.expression
                    or build_expression_from_meetings(list(template.meetings)),
                    template.period,
                    template.school_id,
                    template.section_number,
                    template.section_type,
                    template.term_id,
                    assignment.student_id,
                    template.section_id,
                    template.teacher_id,
                    template.max_enrollment,
                    template.room,
                ]
            )
            dcid += 1


def write_lg_capacity_report(
    path: Path,
    offerings: dict[str, list[SectionOffering]],
    section_assignments: list[SectionAssignment],
    courses: dict[str, Course],
) -> None:
    """Write lg_capacity_report.csv: per-LG-section demand vs capacity.

    For each LG section offering, reports:
      companion_course  — the base small-group course whose teacher this LG section belongs to
      section_id        — PowerSchool section ID
      section_number    — section number
      teacher_id        — teacher (must match the student's base-course teacher)
      max_enrollment    — capacity from the offerings export
      demand            — students successfully placed in the companion course with this teacher
                          (these students *should* fill this LG section)
      placed            — students actually assigned to this LG section
      shortfall         — max(0, demand − max_enrollment); positive means capacity must be raised
    """
    # teacher of each placed (student, course) pair
    placed_teacher: dict[tuple[str, str], str] = {
        (sa.student_id, sa.class_code): sa.teacher_id
        for sa in section_assignments
    }
    # headcount actually assigned per section_id
    placed_count: dict[str, int] = {}
    for sa in section_assignments:
        placed_count[sa.section_id] = placed_count.get(sa.section_id, 0) + 1

    # Aggregate per (lg_course, teacher_id) — a teacher may run multiple LG sections
    # (e.g. A/B day splits), so demand must be compared against their combined capacity.
    # Key: (class_code, teacher_id)  Value: {companion, course_name, sections[], total_cap, demand, placed}
    by_teacher: dict[tuple[str, str], dict] = {}
    for class_code, section_list in offerings.items():
        if "LG" not in class_code:
            continue
        companion_code = class_code.replace("LG", "", 1)
        course = courses.get(class_code)
        course_name = course.name if course else ""
        for offering in section_list:
            key = (class_code, offering.teacher_id)
            if key not in by_teacher:
                by_teacher[key] = {
                    "lg_course": class_code,
                    "lg_course_name": course_name,
                    "companion_course": companion_code,
                    "teacher_id": offering.teacher_id,
                    "sections": [],
                    "total_max_enrollment": 0,
                    "demand": sum(
                        1
                        for (_, cc), tid in placed_teacher.items()
                        if cc == companion_code and tid == offering.teacher_id
                    ),
                    "placed": 0,
                }
            entry = by_teacher[key]
            entry["sections"].append(offering.section_number)
            entry["total_max_enrollment"] += offering.max_enrollment
            entry["placed"] += placed_count.get(offering.section_id, 0)

    rows = []
    for entry in by_teacher.values():
        cap = entry["total_max_enrollment"]
        demand = entry["demand"]
        shortfall = max(0, demand - cap) if cap > 0 else 0
        rows.append((
            entry["lg_course"],
            entry["lg_course_name"],
            entry["companion_course"],
            entry["teacher_id"],
            len(entry["sections"]),
            cap,
            demand,
            entry["placed"],
            shortfall,
        ))

    rows.sort(key=lambda r: (-r[8], r[0], r[3]))  # shortfall desc, then course, teacher

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "lg_course", "lg_course_name", "companion_course",
            "teacher_id", "num_sections", "total_max_enrollment",
            "demand", "placed", "shortfall",
        ])
        for row in rows:
            writer.writerow(row)


def write_schedulecc_csv_from_sections(
    path: Path,
    assignments: list[SectionAssignment],
    offerings: dict[str, list[SectionOffering]],
    starting_dcid: int = 1,
) -> None:
    """Write schedulecc.csv from concrete section assignments."""
    headers = [
        "SCHEDULECC.dcid",
        "SCHEDULECC.BuildID",
        "SCHEDULECC.Course_Number",
        "SCHEDULECC.DateEnrolled",
        "SCHEDULECC.DateLeft",
        "SCHEDULECC.Expression",
        "SCHEDULECC.Period",
        "SCHEDULECC.SchoolID",
        "SCHEDULECC.Section_Number",
        "SCHEDULECC.SectionType",
        "SCHEDULECC.TermID",
        "SCHEDULECC.StudentID",
        "SCHEDULECC.SectionID",
        "SCHEDULECC.TeacherID",
        "SCHEDULECC.MaxEnrollment",
        "SCHEDULECC.MaxCut",
        "SCHEDULECC.Room",
    ]
    # Build a list of all offerings per section_id, preserving every meeting row.
    # Untied sections can have multiple rows in the source export — one per independent
    # meeting (e.g. sid=316848 has rows for "12(B)" and "7(E)").  PowerSchool ScheduleCC
    # requires a separate row for each meeting of an untied section; tied sections only
    # need one row (we use the first occurrence, which carries the full expression).
    offerings_by_id: dict[str, list[SectionOffering]] = {}
    for rows in offerings.values():
        for o in rows:
            offerings_by_id.setdefault(o.section_id, []).append(o)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="	", quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        dcid = starting_dcid
        for assignment in assignments:
            offering_rows = offerings_by_id.get(assignment.section_id)
            if not offering_rows:
                continue
            # For tied sections: one ScheduleCC row using the first (and usually only) row.
            # For untied sections: one ScheduleCC row per meeting so PowerSchool enrolls
            # the student in every independent meeting of the section.
            rows_to_write = [offering_rows[0]] if offering_rows[0].tied else offering_rows
            for offering in rows_to_write:
                # MaxCut=1 tells PowerSchool to enforce the enrollment cap.
                # MaxCut=0 means unlimited (used when MaxEnrollment=0).
                max_cut = 1 if offering.max_enrollment and offering.max_enrollment > 0 else 0
                writer.writerow([
                    str(dcid),
                    offering.build_id,
                    assignment.class_code,
                    offering.date_enrolled,
                    offering.date_left,
                    offering.expression or build_expression_from_meetings(list(offering.meetings)),
                    "",
                    offering.school_id,
                    offering.section_number,
                    offering.section_type,
                    offering.term_id,
                    assignment.student_id,
                    offering.section_id,
                    offering.teacher_id,
                    str(offering.max_enrollment) if offering.max_enrollment else "",
                    str(max_cut),
                    offering.room,
                ])
                dcid += 1
