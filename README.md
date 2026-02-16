# Scheduler

High school scheduling engine: assign students to requested courses (modular schedule, capacity constraints).

## CLI

```bash
# From project root (reqexport format)
python3 scheduler.py --reqexport input/reqexport.txt --output-dir .

# With optional capacity file
python3 scheduler.py --reqexport input/reqexport.txt --capacity capacity.txt
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
