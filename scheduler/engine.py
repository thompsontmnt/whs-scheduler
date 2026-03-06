"""Core scheduling logic. No file I/O, no printing, no CSV writing.

Modular schedule: students may enroll in multiple courses per semester.
Only capacity and reference validity are enforced (no semester-overlap rule).
"""

from scheduler.models import Assignment, Conflict, Course, Request, SectionAssignment, SectionOffering, Student


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

    def schedule_sections(
        self,
        students: dict[str, Student],
        requests: list[Request],
        courses: dict[str, Course],
        offerings: dict[str, list[SectionOffering]],
    ) -> tuple[list[SectionAssignment], list[Conflict]]:
        """Assign students to concrete section offerings with overlap/capacity checks."""
        sorted_requests = sorted(requests, key=lambda r: _request_sort_key(r, students, courses))
        assignments: list[SectionAssignment] = []
        conflicts: list[Conflict] = []

        enrollment: dict[str, int] = {}
        student_meetings: dict[str, set[tuple[int, int]]] = {}
        blocked_offerings = _invalid_offerings(offerings)

        for request in sorted_requests:
            if request.student_id not in students:
                conflicts.append(Conflict(request.student_id, request.class_code, "Student not found"))
                continue
            if request.class_code not in courses:
                conflicts.append(Conflict(request.student_id, request.class_code, "Course not found"))
                continue

            candidate_offerings = offerings.get(request.class_code, [])
            if not candidate_offerings:
                conflicts.append(Conflict(request.student_id, request.class_code, "No section offering"))
                continue

            placed = False
            meetings = student_meetings.setdefault(request.student_id, set())
            for offering in candidate_offerings:
                if offering.section_id in blocked_offerings:
                    continue
                if offering.max_enrollment > 0 and enrollment.get(offering.section_id, 0) >= offering.max_enrollment:
                    continue
                if offering.meetings and meetings.intersection(offering.meetings):
                    continue

                assignments.append(
                    SectionAssignment(
                        student_id=request.student_id,
                        class_code=request.class_code,
                        section_number=offering.section_number,
                        section_id=offering.section_id,
                        teacher_id=offering.teacher_id,
                    )
                )
                enrollment[offering.section_id] = enrollment.get(offering.section_id, 0) + 1
                meetings.update(offering.meetings)
                placed = True
                break

            if not placed:
                conflicts.append(Conflict(request.student_id, request.class_code, "No available non-conflicting section"))

        return (
            sorted(assignments, key=lambda a: (a.student_id, a.class_code, a.section_number, a.section_id)),
            sorted(conflicts, key=lambda c: (c.student_id, c.class_code, c.reason)),
        )


def _has_overlap(left: tuple[tuple[int, int], ...], right: tuple[tuple[int, int], ...]) -> bool:
    return bool(set(left).intersection(right))


def _invalid_offerings(offerings: dict[str, list[SectionOffering]]) -> set[str]:
    """Offerings that violate teacher/room exclusivity at the same time."""
    all_offerings = [offering for rows in offerings.values() for offering in rows]
    invalid: set[str] = set()
    for i, first in enumerate(all_offerings):
        for second in all_offerings[i + 1 :]:
            if not _has_overlap(first.meetings, second.meetings):
                continue
            if first.teacher_id and first.teacher_id == second.teacher_id:
                invalid.add(first.section_id)
                invalid.add(second.section_id)
            if first.room and second.room and first.room == second.room:
                invalid.add(first.section_id)
                invalid.add(second.section_id)
    return invalid
