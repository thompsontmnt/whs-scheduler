"""Core scheduling logic. No file I/O, no printing, no CSV writing.

Modular schedule: students may enroll in multiple courses per semester.
Only capacity and reference validity are enforced (no semester-overlap rule).
"""

from __future__ import annotations

from scheduler.models import Assignment, Conflict, Course, Request, SectionAssignment, SectionOffering, Student


def _request_sort_key(
    request: Request,
    students: dict[str, Student],
    courses: dict[str, Course],
) -> tuple[int, str, int, str, str]:
    """Sort key: grad_year, student_id, full-year first (0), semester_flag, class_code.

    Phase values in the offerings export are intentional and reflect the original DOS Sked
    design: study hall courses (28xx) are Phase=1, the same as core courses. Phase-aware
    sorting is therefore not applied here — all courses compete equally for time slots in
    grad-year / student / class-code order.
    """
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
        # Index of placed section assignments for teacher-matching lookups (e.g. LG courses).
        placed_sections: dict[tuple[str, str], SectionAssignment] = {}
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

            # LG courses: restrict to the section whose teacher matches the student's
            # already-placed companion small-group section.  All LG sections share the
            # same meeting time, so teacher identity is the only meaningful distinguisher.
            # Sort order (alphabetical class_code) guarantees the base course is processed
            # before its LG companion (e.g. "1765A" < "1765ALG"), so placed_sections will
            # already contain the companion when we reach the LG request.
            companion_code = _lg_companion_code(request.class_code)
            if companion_code:
                companion_sa = placed_sections.get((request.student_id, companion_code))
                if companion_sa and companion_sa.teacher_id:
                    candidate_offerings = [
                        o for o in candidate_offerings if o.teacher_id == companion_sa.teacher_id
                    ]

            placed = False
            meetings = student_meetings.setdefault(request.student_id, set())
            for offering in candidate_offerings:
                if offering.section_id in blocked_offerings:
                    continue
                if offering.max_enrollment > 0 and enrollment.get(offering.section_id, 0) >= offering.max_enrollment:
                    continue
                if offering.meetings and meetings.intersection(offering.meetings):
                    continue

                sa = SectionAssignment(
                    student_id=request.student_id,
                    class_code=request.class_code,
                    section_number=offering.section_number,
                    section_id=offering.section_id,
                    teacher_id=offering.teacher_id,
                )
                assignments.append(sa)
                placed_sections[(request.student_id, request.class_code)] = sa
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


def _lg_companion_code(class_code: str) -> str | None:
    """Return the companion small-group base course code for an LG course, or None.

    LG courses are companion sections for large-group instruction.  Their codes embed
    "LG" immediately before any trailing section letter (or at the end):
      1765ALG  → 1765A   (small-group base is 1765A)
      1105LGA  → 1105A   (small-group base is 1105A)
      1809LG   → 1809
      1843LG   → 1843

    The rule is simply: remove the first occurrence of "LG" from the code.
    Returns None for courses that do not contain "LG".
    """
    if "LG" not in class_code:
        return None
    return class_code.replace("LG", "", 1)


def _has_overlap(left: tuple[tuple[int, int], ...], right: tuple[tuple[int, int], ...]) -> bool:
    return bool(set(left).intersection(right))


def _is_exclusive_room(room: str) -> bool:
    normalized = room.strip().upper()
    return normalized not in {"", "NA", "N/A", "NONE", "TBD"}


def _invalid_offerings(offerings: dict[str, list[SectionOffering]]) -> set[str]:
    """Offerings that violate teacher/room exclusivity at the same time."""
    all_offerings = [offering for rows in offerings.values() for offering in rows]
    invalid: set[str] = set()
    for i, first in enumerate(all_offerings):
        for second in all_offerings[i + 1 :]:
            if first.class_code == second.class_code:
                continue
            if not _has_overlap(first.meetings, second.meetings):
                continue
            same_teacher = first.teacher_id and first.teacher_id == second.teacher_id
            same_room = (
                _is_exclusive_room(first.room)
                and _is_exclusive_room(second.room)
                and first.room == second.room
            )
            # Only globally invalidate offerings when the overlap is a true duplicate:
            # same teacher in the same meaningful room at the same time.
            # Teacher-only and room-only overlaps are too aggressive for the exported
            # PowerSchool data because many legitimate cross-listed/shared-space rows
            # would otherwise be removed before scheduling.
            if same_teacher and same_room:
                invalid.add(first.section_id)
                invalid.add(second.section_id)
    return invalid
