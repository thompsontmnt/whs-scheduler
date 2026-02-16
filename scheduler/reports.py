"""Output formatting (CSV generation)."""

import csv
import io
from pathlib import Path

from scheduler.models import Assignment, Conflict, Course, Student


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
