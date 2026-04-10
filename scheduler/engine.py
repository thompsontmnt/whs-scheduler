"""Core scheduling logic. No file I/O, no printing, no CSV writing.

Modular schedule: students may enroll in multiple courses per semester.
Only capacity and reference validity are enforced (no semester-overlap rule).
"""

from __future__ import annotations

from collections import defaultdict

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


def _schedule_multi_phase(
    student_id: str,
    class_code: str,
    all_offerings: list[SectionOffering],
    student_meetings: set[tuple[int, int]],
    enrollment: dict[str, int],
    section_all_meetings: dict[str, set[tuple[int, int]]],
) -> tuple[list[SectionOffering], set[tuple[int, int]]]:
    """Assign a student to one section per required phase type, all the same teacher.

    Phase semantics for multi-phase untied courses:
      Phase 1 = Gradebook section (administrative; assigned without blocking conflict check)
      Phase 2 = Large-group or alternate meeting embedded within the same course code
      Phase 3+ = Weekday meeting slots (Monday, Tuesday, Wednesday, Thursday, Friday)

    Teacher-tied rule: all phase-3+ sections must share the same teacher_id.
    Phase 1 and Phase 2 are also matched to the chosen teacher where possible.

    A single section_id may cover multiple phases (e.g. section 317016 appears as both
    Phase 4/Tuesday and Phase 6/Friday). When that section is committed for one phase,
    it automatically satisfies the other phase without adding a duplicate enrollment.

    Returns (chosen_offerings, committed_meetings):
      chosen_offerings  — one SectionOffering per unique section_id selected
      committed_meetings — all (day, mod) slots occupied by the chosen sections
    Returns ([], set()) when no valid teacher assignment can be found.
    """
    # Group offerings by phase value
    by_phase: dict[int, list[SectionOffering]] = defaultdict(list)
    for o in all_offerings:
        by_phase[o.phase].append(o)

    phases = sorted(by_phase.keys())
    meeting_phases = [p for p in phases if p >= 3]

    if not meeting_phases:
        # No weekday meeting phases — caller should fall back to single-phase logic
        return [], set()

    # Build teacher → {phase → [sorted offerings]} for meeting phases
    teacher_opts: dict[str, dict[int, list[SectionOffering]]] = {}
    for phase in meeting_phases:
        for o in by_phase[phase]:
            tid = o.teacher_id
            if tid not in teacher_opts:
                teacher_opts[tid] = defaultdict(list)
            teacher_opts[tid][phase].append(o)

    # Qualify: teacher must have at least one option in every required meeting phase
    qualified_teachers = sorted(
        tid for tid, opts in teacher_opts.items()
        if all(p in opts for p in meeting_phases)
    )

    for teacher_id in qualified_teachers:
        chosen: list[SectionOffering] = []
        ok = True
        committed_meetings: set[tuple[int, int]] = set()
        committed_sids: set[str] = set()

        # --- Phase 3+ (weekday meetings): one non-conflicting section per phase ---
        for phase in meeting_phases:
            # Sort by current enrollment (least-loaded first) for even distribution
            options = sorted(
                teacher_opts[teacher_id][phase],
                key=lambda o: (enrollment.get(o.section_id, 0), o.section_id),
            )
            placed = False
            for o in options:
                if o.section_id in committed_sids:
                    # Already committed for another phase — this section covers this phase too
                    placed = True
                    break
                # Use only THIS offering row's meetings, not section_all_meetings.
                # A section_id may appear in both Phase 2 (LG/Monday) and Phase 3+ rows;
                # section_all_meetings would merge those, but Phase 2 meetings are handled
                # separately via standalone LG course requests and must not block Phase 3+
                # placement. Using o.meetings isolates each phase's actual meeting time.
                phase_meetings = set(o.meetings)
                cap_ok = o.max_enrollment <= 0 or enrollment.get(o.section_id, 0) < o.max_enrollment
                no_conflict = not (phase_meetings & student_meetings) and not (phase_meetings & committed_meetings)
                if cap_ok and no_conflict:
                    chosen.append(o)
                    committed_meetings |= phase_meetings
                    committed_sids.add(o.section_id)
                    placed = True
                    break

            if not placed:
                ok = False
                break

        if not ok:
            continue

        # Phase 2 is intentionally skipped here. All LG sections at WHS have their own
        # course code (e.g. 1207LG) and are processed as separate requests via the
        # single-phase LG companion-matching path. Enrolling Phase 2 here would create
        # duplicate LG rows for students who also have a standalone LG request.

        # --- Phase 1 (Gradebook): same teacher; no conflict check (administrative) ---
        for o in by_phase.get(1, []):
            if o.section_id in committed_sids:
                break
            if o.teacher_id == teacher_id:
                cap_ok = o.max_enrollment <= 0 or enrollment.get(o.section_id, 0) < o.max_enrollment
                if cap_ok:
                    chosen.append(o)
                    committed_sids.add(o.section_id)
                    # Deliberately NOT added to committed_meetings — gradebook is
                    # administrative and must not block placement of real course sections.
                    break

        return chosen, committed_meetings

    # No valid teacher found for all required meeting phases
    return [], set()


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
        """Assign students to concrete section offerings with overlap/capacity checks.

        Multi-phase courses (any course with Phase >= 3 offerings) require one section
        enrollment per phase type, all from the same teacher. Single-phase courses use
        the original one-section-per-request logic.
        """
        sorted_requests = sorted(requests, key=lambda r: _request_sort_key(r, students, courses))
        assignments: list[SectionAssignment] = []
        conflicts: list[Conflict] = []

        enrollment: dict[str, int] = {}
        student_meetings: dict[str, set[tuple[int, int]]] = {}
        # Index of placed section assignments for teacher-matching lookups (e.g. LG courses).
        placed_sections: dict[tuple[str, str], SectionAssignment] = {}
        blocked_offerings = _invalid_offerings(offerings)

        # Pre-compute: for each section_id, accumulate ALL meetings from every offering row.
        # A section_id can appear in multiple rows (one per meeting day for untied sections),
        # so conflict checking must consider the complete set of meetings for that section.
        section_all_meetings: dict[str, set[tuple[int, int]]] = defaultdict(set)
        for rows in offerings.values():
            for o in rows:
                section_all_meetings[o.section_id].update(o.meetings)

        # Multi-phase courses have at least one offering with phase >= 3.
        # Phase 3+ represents weekday meeting slots (Mon/Tue/Wed/Thu/Fri).
        # Students must be enrolled in one section per phase, all same teacher.
        multi_phase_courses: set[str] = {
            class_code
            for class_code, rows in offerings.items()
            if any(o.phase >= 3 for o in rows)
        }

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

            meetings = student_meetings.setdefault(request.student_id, set())

            # ── Multi-phase path ──────────────────────────────────────────────────────
            if request.class_code in multi_phase_courses:
                chosen, committed = _schedule_multi_phase(
                    request.student_id,
                    request.class_code,
                    candidate_offerings,
                    meetings,
                    enrollment,
                    section_all_meetings,
                )
                if chosen:
                    primary_sa: SectionAssignment | None = None
                    for offering in chosen:
                        sa = SectionAssignment(
                            student_id=request.student_id,
                            class_code=request.class_code,
                            section_number=offering.section_number,
                            section_id=offering.section_id,
                            teacher_id=offering.teacher_id,
                        )
                        assignments.append(sa)
                        enrollment[offering.section_id] = enrollment.get(offering.section_id, 0) + 1
                        # First phase-3+ offering is the "primary" section used for LG
                        # companion teacher-matching (e.g. 1920LG looks up 1920's teacher).
                        if primary_sa is None and offering.phase >= 3:
                            primary_sa = sa
                    # Fall back to first offering if no phase-3+ section found
                    if primary_sa is None:
                        primary_sa = SectionAssignment(
                            student_id=request.student_id,
                            class_code=request.class_code,
                            section_number=chosen[0].section_number,
                            section_id=chosen[0].section_id,
                            teacher_id=chosen[0].teacher_id,
                        )
                    placed_sections[(request.student_id, request.class_code)] = primary_sa
                    meetings.update(committed)
                else:
                    conflicts.append(Conflict(
                        request.student_id,
                        request.class_code,
                        "No available non-conflicting section",
                    ))

            # ── Single-phase path ─────────────────────────────────────────────────────
            else:
                # LG courses: restrict to the section whose teacher matches the student's
                # already-placed companion small-group section.
                companion_code = _lg_companion_code(request.class_code)
                if companion_code:
                    companion_sa = placed_sections.get((request.student_id, companion_code))
                    if companion_sa and companion_sa.teacher_id:
                        candidate_offerings = [
                            o for o in candidate_offerings if o.teacher_id == companion_sa.teacher_id
                        ]

                placed = False
                for offering in candidate_offerings:
                    if offering.section_id in blocked_offerings:
                        continue
                    if offering.max_enrollment > 0 and enrollment.get(offering.section_id, 0) >= offering.max_enrollment:
                        continue
                    # Use section_all_meetings so tied sections with compound expressions
                    # and untied sections with multiple meeting rows are both correctly
                    # conflict-checked against the student's full placed-meeting set.
                    sid_meetings = section_all_meetings.get(offering.section_id, set(offering.meetings))
                    if sid_meetings and meetings.intersection(sid_meetings):
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
                    meetings.update(sid_meetings)
                    placed = True
                    break

                if not placed:
                    conflicts.append(Conflict(
                        request.student_id,
                        request.class_code,
                        "No available non-conflicting section",
                    ))

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
    """Return the set of section IDs that should be excluded from scheduling.

    The PowerSchool section-offerings export represents an already-validated
    master schedule.  Co-teaching (same teacher, same room, same time across
    different course codes) and shared large-group spaces (multiple sections
    from different courses in the same room simultaneously) are both
    intentional patterns in this data and must not be flagged.

    No sections are currently excluded — this function is retained as a hook
    for future data-quality checks if needed.
    """
    return set()
