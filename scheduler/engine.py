"""Core scheduling logic. No file I/O, no printing, no CSV writing.

Modular schedule: students may enroll in multiple courses per semester.
Only capacity and reference validity are enforced (no semester-overlap rule).
"""

from scheduler.models import Assignment, Conflict, Course, Request, Student


def _request_sort_key(
    request: Request,
    students: dict[str, Student],
    courses: dict[str, Course],
) -> tuple[int, str, int, str, str]:
    """Sort key: grad_year, student_id, full-year first (0), semester_flag, class_code."""
    student = students.get(request.student_id)
    course = courses.get(request.class_code)
    grad_year = student.grad_year if student else 0
    # Full year (F1) first: 0 for F1, 1 otherwise
    duration_priority = 0 if (course and course.duration_flag == "F1") else 1
    semester_flag = course.semester_flag if course else ""
    return (grad_year, request.student_id, duration_priority, semester_flag, request.class_code)


class Scheduler:
    """Deterministic scheduler. Modular: multiple courses per semester allowed."""

    def __init__(self, capacity_by_class: dict[str, int]) -> None:
        self._capacity_by_class = dict(capacity_by_class)

    def schedule(
        self,
        students: dict[str, Student],
        requests: list[Request],
        courses: dict[str, Course],
    ) -> tuple[list[Assignment], list[Conflict]]:
        """
        Assign students to requested courses. Enforces: student/course exist, capacity.
        Modular schedule: no limit on courses per semester per student.
        Returns (assignments, conflicts). No file I/O or side effects.
        """
        # Deterministic order: sort requests
        sorted_requests = sorted(
            requests,
            key=lambda r: _request_sort_key(r, students, courses),
        )

        assignments: list[Assignment] = []
        conflicts: list[Conflict] = []

        # enrollment[class_code] = number of students assigned
        enrollment: dict[str, int] = {code: 0 for code in self._capacity_by_class}
        for code in courses:
            if code not in enrollment:
                enrollment[code] = 0

        for request in sorted_requests:
            if request.student_id not in students:
                conflicts.append(
                    Conflict(
                        student_id=request.student_id,
                        class_code=request.class_code,
                        reason="Student not found",
                    )
                )
                continue

            if request.class_code not in courses:
                conflicts.append(
                    Conflict(
                        student_id=request.student_id,
                        class_code=request.class_code,
                        reason="Course not found",
                    )
                )
                continue

            capacity = self._capacity_by_class.get(
                request.class_code, 999_999
            )  # unlimited if not configured

            if enrollment[request.class_code] >= capacity:
                conflicts.append(
                    Conflict(
                        student_id=request.student_id,
                        class_code=request.class_code,
                        reason="Class full",
                    )
                )
                continue

            # Assign (modular: no semester-overlap check)
            assignments.append(
                Assignment(student_id=request.student_id, class_code=request.class_code)
            )
            enrollment[request.class_code] = enrollment.get(request.class_code, 0) + 1

        # Deterministic output order
        assignments_sorted = sorted(assignments, key=(lambda a: (a.student_id, a.class_code)))
        conflicts_sorted = sorted(
            conflicts,
            key=(lambda c: (c.student_id, c.class_code)),
        )
        return (assignments_sorted, conflicts_sorted)
