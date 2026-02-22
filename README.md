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

To start aligning with PowerSchool import requirements, provide a tab-delimited section template file:

`class_code	expression	section_number	teacher_id	section_id	term_id	school_id	build_id	period	day	mod`

Example:

`1637A		16	22793	314419	3501	25	3558		1	6`

If `expression` is blank and `day` + `mod` rows are present for the same section, the exporter now builds expression text automatically (e.g. `1(A-B)`, `1-2(C)`).

If multiple rows exist for a class code, assignments are distributed round-robin across those template rows.
