# Scheduler

High school scheduling engine: assign students to requested courses (modular schedule, capacity constraints).

## CLI

```bash
# From project root (reqexport format)
python3 scheduler.py --reqexport input/reqexport.txt --output-dir .

# With optional capacity file
python3 scheduler.py --reqexport input/reqexport.txt --capacity capacity.txt

# With section templates to produce PowerSchool-style schedulecc.csv
python3 scheduler.py --reqexport input/reqexport.txt --section-templates input/section_templates.txt
```

## Web app

Upload tab-delimited reqexport (and optional capacity file), get assignments and conflicts as CSV downloads.

**Install and run:**

```bash
pip install -r requirements.txt
uvicorn scheduler.app:app --reload
```

Then open http://127.0.0.1:8000 . Use the form to upload your reqexport file (and optionally a capacity file), then download `assignments.csv` and `conflicts.csv`.

## Input

- **Reqexport:** Tab-delimited with columns Student Name, Student Number, Next Grade, School, Dept, Course #, Course_Name, Credits, …
- **Capacity (optional):** Tab-delimited, one line per class: `class_code<TAB>capacity`.

## Output

- **assignments.csv:** student_id, student_name, class_code, course_name, semester
- **conflicts.csv:** student_id, student_name, class_code, reason
- **schedulecc.csv (optional):** PowerSchool-style tab-delimited export when `--section-templates` is provided

## Section template input (optional)

To start aligning with PowerSchool import requirements, provide a tab-delimited section template file (see starter files `input/section_definitions_template.txt` and shareable CSV `input/section_definitions_template.csv`):

`class_code	expression	section_number	teacher_id	section_id	term_id	build_id	period	date_enrolled	date_left	max_enrollment	room	section_type	day	mod	tied`

(`school_id` can be omitted for single-school use; parser defaults it to `25`.)

Example:

`1920		1	22793	314419	3501	3558		44928	45072	25	201		1	2	tied`

If `expression` is blank and `day` + `mod` rows are present for the same section, the exporter now builds expression text automatically (e.g. `1(A-B)`, `1-2(C)`).

Optional import fields from your PowerSchool template (`date_enrolled`, `date_left`, `max_enrollment`, `room`, `section_type`) are carried through to `schedulecc.csv` when present.

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
