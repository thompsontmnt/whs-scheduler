# Scheduler

High school scheduling engine: assign students to requested courses (modular schedule, capacity constraints).

## CLI

```bash
# From project root (reqexport format)
python3 scheduler.py --reqexport input/reqexport.txt --output-dir .

# With optional capacity file
python3 scheduler.py --reqexport input/reqexport.txt --capacity capacity.txt

# With section templates to produce PowerSchool-style schedulecc.txt
python3 scheduler.py --reqexport input/reqexport.txt --section-templates input/section_templates.txt

# Preferred: concrete section offerings + requests export (direct schedulecc placement; no reqexport needed)
python3 scheduler.py --requests-export 'input/new/ScheduleRequests.export.txt' --section-offerings 'input/new/Sem 1 sample sked export with phases.txt' --output-dir .
```

## Web app

Upload two tab-delimited files (ScheduleRequests export + section offerings export), get `schedulecc.txt`, `dropped_by_reason.txt`, plus assignments/conflicts text downloads.

**Install and run:**

```bash
pip install -r requirements.txt
uvicorn scheduler.app:app --reload
```

Then open http://127.0.0.1:8000 . Use the form to upload `ScheduleRequests.export.txt` and your section offerings file (for example Sem 1 export with phases), then download `schedulecc.txt`, `dropped_by_reason.txt`, `assignments.txt`, and `conflicts.txt`.

## Input

- **Reqexport:** Tab-delimited with columns Student Name, Student Number, Next Grade, School, Dept, Course #, Course_Name, Credits, …
- **Capacity (optional):** Tab-delimited, one line per class: `class_code<TAB>capacity`.

## Output

- **assignments.txt:** student_id, student_name, class_code, course_name, semester
- **conflicts.txt:** student_id, student_name, class_code, reason
- **schedulecc.txt (optional):** PowerSchool-style tab-delimited export when `--section-templates` is provided
- **dropped_by_reason.txt (section-offerings mode):** requests removed during reconciliation before scheduling (for PO review)

## Section template input (optional)

To start aligning with PowerSchool import requirements, provide a tab-delimited section template file (see starter files `input/section_definitions_template.txt` and shareable CSV `input/section_definitions_template.csv`):

`class_code	expression	section_number	teacher_id	section_id	term_id	build_id	period	date_enrolled	date_left	max_enrollment	room	section_type	day	mod	tied`

(`school_id` can be omitted for single-school use; parser defaults it to `25`.)

Example:

`1920		1	22793	314419	3501	3558		44928	45072	25	201		1	2	tied`

If `expression` is blank and `day` + `mod` rows are present for the same section, the exporter now builds expression text automatically (e.g. `1(A-B)`, `1-2(C)`).

Optional import fields from your PowerSchool template (`date_enrolled`, `date_left`, `max_enrollment`, `room`, `section_type`) are carried through to `schedulecc.txt` when present.

If multiple rows exist for a class code, assignments are distributed round-robin across those template rows.


Notes:
- Day mapping is fixed: `1=A` (Mon), `2=B` (Tue), `3=C` (Wed), `4=D` (Thu), `5=E` (Fri).
- Expression formatting follows PowerSchool import rules:
  - Consecutive days/mods use hyphen ranges (for example `1(A-B)` and `4-6(B-E)`).
  - Non-consecutive days stay in the same token and use commas (for example `4-6(B,E)` and `9-10(A-B,D)`).
  - Spaces separate different period expressions (for example `9-10(A-B,D) 12(C) 9-10(E)`).
- For tied rows (default), matching section-template rows are merged before expression generation.
- For `tied=untied`, rows are kept as separate expression cells instead of being merged.
- Large-group sections should be exported as separate course rows (for example course `1920` with LG section `1920LG`).
- BuildID and SchoolID are typically constant for a given import file; TermID is normally one value for all semester 1 sections and another for semester 2.


## Section offerings input (preferred pipeline)

When `--section-offerings` is provided, the scheduler assigns students directly to concrete section rows from a PowerSchool-style section export (for example `input/new/Sem 1 sample sked export with phases.txt`) and writes `schedulecc.txt` from those selected placements.

Supported constraints in this mode:
- Student no-overlap across meeting times parsed from `Expression`.
- Per-section capacity via `MaxEnrollment`.
- Teacher/room exclusivity at overlapping meeting times (conflicting offerings are excluded).
- Requests for non-offered course codes are dropped during reconciliation.
- Weekday variant requests in the same family are collapsed to one request per student; for lunch family `2912*`, dropped variants are labeled `lunch_auto_semester2` to represent inferred Sem 2 placement.

You can pair this with `--requests-export` (for example `input/new/ScheduleRequests.export.txt`) so requests come from `Student_Number` + `CourseNumber`.

If `--reqexport` is omitted, the CLI now builds minimal student references from `ScheduleRequests.export` and minimal course references from `--section-offerings`, so these two `input/new` files are sufficient for scheduling/export.

In section-offerings mode, the CLI also writes `dropped_by_reason.txt` with columns `student_id, student_name, class_code, reason, detail` (for example `no_section_offering`, `weekday_variant_collapsed`, and `lunch_auto_semester2`) to support PO data review and section-adjustment planning.
