"""Command-line entry point. Later replaceable by FastAPI wrapper."""

import argparse
import csv
from pathlib import Path

from scheduler.engine import Scheduler
from scheduler.models import Assignment
from scheduler.parsers import (
    load_courses,
    load_courses_from_reqexport,
    load_courses_from_requests_export,
    load_courses_from_section_offerings,
    load_requests,
    load_requests_export,
    load_students_from_requests_export,
    load_requests_from_reqexport,
    load_section_offerings,
    load_section_templates,
    load_students,
    load_students_from_reqexport,
    reconcile_requests_to_offerings,
)
from scheduler.reports import (
    write_assignments_csv,
    write_conflicts_csv,
    write_lg_capacity_report,
    write_schedulecc_csv,
    write_schedulecc_csv_from_sections,
    write_dropped_by_reason_csv,
)


def load_capacity(path: Path) -> dict[str, int]:
    """Load capacity per class from tab-delimited file: class_code, capacity."""
    capacity_by_class: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 2:
                continue
            class_code = row[0].strip()
            capacity = int(row[1].strip())
            capacity_by_class[class_code] = capacity
    return capacity_by_class


def main() -> None:
    parser = argparse.ArgumentParser(
        description="High school scheduling engine — deterministic, semester-aware."
    )
    parser.add_argument(
        "--students",
        type=Path,
        default=Path("students.txt"),
        help="Path to students file (tab-delimited)",
    )
    parser.add_argument(
        "--requests",
        type=Path,
        default=Path("requests.txt"),
        help="Path to requests file (tab-delimited)",
    )
    parser.add_argument(
        "--prior",
        type=Path,
        default=Path("PRIOR.TXT"),
        help="Path to course metadata (PRIOR.TXT)",
    )
    parser.add_argument(
        "--capacity",
        type=Path,
        default=None,
        help="Path to capacity file (tab-delimited: class_code, capacity). If omitted, all classes get default capacity.",
    )
    parser.add_argument(
        "--default-capacity",
        type=int,
        default=999,
        help="Default capacity per class when --capacity file is not used (default: 999)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for assignments.csv and conflicts.csv",
    )
    parser.add_argument(
        "--reqexport",
        type=Path,
        default=None,
        help="Use reqexport-style file: students, requests, and courses derived from this one file (ignores --students, --requests, --prior)",
    )

    parser.add_argument(
        "--section-offerings",
        type=Path,
        default=None,
        help="Tab-delimited section export with concrete section rows (TermID, Course_Number, Teacher, Expression, Section_Number, Room, MaxEnrollment, Tied, Phase).",
    )
    parser.add_argument(
        "--requests-export",
        type=Path,
        default=None,
        help="Optional PowerSchool ScheduleRequests export (uses Student_Number + CourseNumber for requests).",
    )
    parser.add_argument(
        "--section-templates",
        type=Path,
        default=None,
        help="Optional tab-delimited file used to write schedulecc.csv (columns: class_code, expression, section_number, teacher_id, section_id, term_id, school_id, build_id, period)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.reqexport is not None and args.reqexport.exists():
        students = load_students_from_reqexport(args.reqexport)
        requests = load_requests_from_reqexport(args.reqexport)
        courses = load_courses_from_reqexport(args.reqexport)
    else:
        students = load_students(args.students)
        requests = load_requests(args.requests)
        courses = load_courses(args.prior)

    if args.requests_export is not None and args.requests_export.exists():
        requests = load_requests_export(args.requests_export)
        if args.reqexport is None or not args.reqexport.exists():
            students = load_students_from_requests_export(args.requests_export)
            courses = load_courses_from_requests_export(args.requests_export)
            if args.section_offerings is not None and args.section_offerings.exists():
                courses.update(load_courses_from_section_offerings(args.section_offerings))

    if args.capacity is not None and args.capacity.exists():
        capacity_by_class = load_capacity(args.capacity)
    else:
        capacity_by_class = {code: args.default_capacity for code in courses}

    scheduler = Scheduler(capacity_by_class=capacity_by_class)

    assignments_path = args.output_dir / "assignments.txt"
    conflicts_path = args.output_dir / "conflicts.txt"

    if args.section_offerings is not None and args.section_offerings.exists():
        offerings = load_section_offerings(args.section_offerings)
        requests, dropped_rows = reconcile_requests_to_offerings(requests, offerings)
        section_assignments, conflicts = scheduler.schedule_sections(students, requests, courses, offerings)
        class_assignments = [
            # reuse existing assignments.csv schema
            Assignment(student_id=a.student_id, class_code=a.class_code)
            for a in section_assignments
        ]
        write_assignments_csv(assignments_path, class_assignments, students, courses)
        write_conflicts_csv(conflicts_path, conflicts, students)
        schedulecc_path = args.output_dir / "schedulecc.txt"
        dropped_path = args.output_dir / "dropped_by_reason.txt"
        write_schedulecc_csv_from_sections(schedulecc_path, section_assignments, offerings)
        write_dropped_by_reason_csv(dropped_path, dropped_rows, students)
        lg_capacity_path = args.output_dir / "lg_capacity_report.txt"
        write_lg_capacity_report(lg_capacity_path, offerings, section_assignments, courses)
        print(f"Wrote {assignments_path} ({len(class_assignments)} assignments)")
        print(f"Wrote {conflicts_path} ({len(conflicts)} conflicts)")
        print(f"Wrote {schedulecc_path}")
        print(f"Wrote {dropped_path} ({len(dropped_rows)} dropped requests)")
        print(f"Wrote {lg_capacity_path}")
    else:
        assignments, conflicts = scheduler.schedule(students, requests, courses)
        write_assignments_csv(assignments_path, assignments, students, courses)
        write_conflicts_csv(conflicts_path, conflicts, students)

        print(f"Wrote {assignments_path} ({len(assignments)} assignments)")
        print(f"Wrote {conflicts_path} ({len(conflicts)} conflicts)")

        if args.section_templates is not None and args.section_templates.exists():
            section_templates = load_section_templates(args.section_templates)
            schedulecc_path = args.output_dir / "schedulecc.txt"
            write_schedulecc_csv(schedulecc_path, assignments, section_templates)
            print(f"Wrote {schedulecc_path}")


if __name__ == "__main__":
    main()
