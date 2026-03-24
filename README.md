# WHS Scheduler

Section-placement engine for Westside High School (Omaha). Ingests two PowerSchool export files, assigns students to course sections, and outputs a `schedulecc.txt` PowerSchool import file plus diagnostic reports.

## Hosted web app

Upload files and download results directly:
**https://whs-scheduler.onrender.com**

## CLI

```bash
python3 scheduler.py \
  --requests-export 'input/new/ScheduleRequests.export.txt' \
  --section-offerings 'input/new/Sem 1 sample sked export with phases.txt' \
  --output-dir /tmp/out
```

## Run locally

```bash
pip install -r requirements.txt
uvicorn scheduler.app:app --reload
# open http://127.0.0.1:8000
```

## Inputs

| File | Description |
|---|---|
| `ScheduleRequests.export.txt` | Tab-delimited PowerSchool export: `StudentID`, `Student_Number`, `CourseNumber`, `YearID` |
| Section offerings export | Tab-delimited PowerSchool section export with columns: `TermID`, `Course_Number`, `Teacher`, `Expression`, `Section_Number`, `Room`, `MaxEnrollment`, `Phase`, etc. |

**Note:** The section offerings export currently contains two columns both labeled `MaxEnrollment`. Python's `csv.DictReader` reads the last occurrence — the engine warns about this at startup. The first column is the enrollment cap; the second should be `MaxCut` (0/1 flag for whether to enforce the cap). Both are written correctly to `schedulecc.txt`.

## Outputs

| File | Description |
|---|---|
| `schedulecc.txt` | PowerSchool import file — one row per student-section assignment with `MaxEnrollment` and `MaxCut` |
| `conflicts.txt` | Unplaced requests with reason |
| `dropped_by_reason.txt` | Requests removed during reconciliation (e.g. Sem 2 courses, lunch deduplication) |
| `assignments.txt` | Placed assignments reference (student + course, no section detail) |
| `lg_capacity_report.txt` | Per-LG-section demand vs capacity by teacher, with shortfall flagged |

## Domain rules

- **Day mapping:** 1=A (Mon), 2=B (Tue), 3=C (Wed), 4=D (Thu), 5=E (Fri)
- **Phase:** encodes scheduling context in the offerings export (0=homeroom, 1=core/seminar, 2=LG). Study hall courses (28xx) are Phase=1 by design.
- **LG courses** (e.g. `1765ALG`) are companion sections — any LG section is valid as long as its teacher matches the student's small-group section teacher. LG sections of the same course all share a meeting time by design and do not conflict with each other.
- **28xx range** contains seminar (important — students must be placed) and study center (unplaced conflicts are acceptable). `2836B` (Mindset Mastery) is Sem 2 only.
- **Lunch (`2912*`):** one request per student per day; duplicate weekday requests are auto-deferred to Sem 2.
- **`no_section_offering` drops** are expected for Sem 2 courses when running a Sem 1 offerings file.

## Expression format

PowerSchool expression syntax used in both input and output:

- Consecutive days/mods use hyphens: `1(A-B)`, `4-6(B-E)`
- Non-consecutive use commas: `4-6(B,E)`, `9-10(A-B,D)`
- Spaces separate different period groups: `9-10(A-B,D) 12(C) 9-10(E)`

## Current baseline (Sem 1)

| Metric | Count |
|---|---|
| Assignments | 24,791 |
| Conflicts | 1,304 |
| Dropped (reconciliation) | 15,140 |
| Students | 2,143 |

Remaining conflicts are structural (LG time-slot collisions, core course collisions, lunch period conflicts, seminar) — not resolvable by the engine without master schedule changes.
