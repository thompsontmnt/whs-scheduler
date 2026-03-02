"""Output formatting (CSV generation)."""

import csv
import io
from pathlib import Path

from scheduler.expression import build_expression_from_meetings
from scheduler.models import Assignment, Conflict, Course, SectionTemplate, Student


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
        "SCHEDULECC.Expression",
        "SCHEDULECC.Period",
        "SCHEDULECC.SchoolID",
        "SCHEDULECC.Section_Number",
        "SCHEDULECC.TermID",
        "SCHEDULECC.StudentID",
        "SCHEDULECC.SectionID",
        "SCHEDULECC.TeacherID",
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
                    template.expression
                    or build_expression_from_meetings(list(template.meetings)),
                    template.period,
                    template.school_id,
                    template.section_number,
                    template.term_id,
                    assignment.student_id,
                    template.section_id,
                    template.teacher_id,
                ]
            )
            dcid += 1
