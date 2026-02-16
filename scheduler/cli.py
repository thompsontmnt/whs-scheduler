"""Command-line entry point. Later replaceable by FastAPI wrapper."""

import argparse
import csv
from pathlib import Path

from scheduler.engine import Scheduler
from scheduler.parsers import (
    load_courses,
    load_courses_from_reqexport,
    load_requests,
    load_requests_from_reqexport,
    load_students,
    load_students_from_reqexport,
)
from scheduler.reports import write_assignments_csv, write_conflicts_csv


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
    args = parser.parse_args()

    if args.reqexport is not None and args.reqexport.exists():
        students = load_students_from_reqexport(args.reqexport)
        requests = load_requests_from_reqexport(args.reqexport)
        courses = load_courses_from_reqexport(args.reqexport)
    else:
        students = load_students(args.students)
        requests = load_requests(args.requests)
        courses = load_courses(args.prior)

    if args.capacity is not None and args.capacity.exists():
        capacity_by_class = load_capacity(args.capacity)
    else:
        capacity_by_class = {code: args.default_capacity for code in courses}

    scheduler = Scheduler(capacity_by_class=capacity_by_class)
    assignments, conflicts = scheduler.schedule(students, requests, courses)

    assignments_path = args.output_dir / "assignments.csv"
    conflicts_path = args.output_dir / "conflicts.csv"
    write_assignments_csv(assignments_path, assignments, students, courses)
    write_conflicts_csv(conflicts_path, conflicts, students)

    print(f"Wrote {assignments_path} ({len(assignments)} assignments)")
    print(f"Wrote {conflicts_path} ({len(conflicts)} conflicts)")


if __name__ == "__main__":
    main()
