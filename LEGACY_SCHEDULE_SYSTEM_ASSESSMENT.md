# Schedule Building System – Inputs & Algorithm Assessment

This document summarizes the data files and inferred logic of the DOS schedule builder (e.g. ClasSchedule) so you can replicate or adapt it in Python.

---

## 1. File Inventory & Roles

| File | Location | Purpose |
|------|----------|--------|
| **PRIOR.TXT** | Sked/ | **Course catalog**: course ID, code, title, frequency, semester. Master list of all offerable courses. |
| **CH.TXT** | Sked/ | **Class/section definitions**: which sections exist, teacher, room(s), capacity. The “built” schedule of sections. |
| **SH.TXT** | Sked/ | **Student schedule (output)**: one row per student-per-course; which section/period the student is in. |
| **TR.TXT** | Sked/ | **Teacher roster**: teacher_id → name. |
| **SD.TXT** | Sked/ | **Student directory**: student_id → name (students in the building). |
| **RR.TXT** | Sked/ | **Room list**: room codes (e.g. 115, 223, AUDI, 119B). |
| **Requests.txt** (etc.) | SKEDFiles/ | **Student course requests**: student_id, course_id pairs. Input to the scheduler. |
| **students.txt** | SKEDFiles/ | **Student list with homeroom/grade**: name, id, two repeat columns (homeroom?), gender, grad year. |

---

## 2. Input Data Structures

### 2.1 Course catalog – PRIOR.TXT

- **Delimiter**: comma.
- **Columns** (in order):
  1. **course_id** (int) – e.g. 1012, 1207, 2811.
  2. **code** – e.g. "MA 1605", "SC 1805", "EN 1209".
  3. **course_name** – e.g. "ALGEBRA 1 S1DNU", "BIOLOGY SEM1", "ENGLISH 1(H) S1".
  4. **frequency** – e.g. "F1", "F5", "F6" (likely meetings per week or block pattern).
  5. **semester** – e.g. "S1", "S2".

- **Special IDs**: 28xx often = study hall / non-class (2811, 2818, 2802, etc.); 29xx = support/speech (2900, 2966, 2975, etc.); 52xx/55xx = guidance/special (e.g. 5291, 5512).

### 2.2 Class/section definitions – CH.TXT

- **Delimiter**: tab.
- **Columns** (inferred):
  1. **course_id**
  2. **col2** – constant `2` (likely semester or term).
  3. **period_or_block** – integer (e.g. 1–6 or 1–7).
  4. **section_number** – section within that course (e.g. 1–18).
  5. **teacher_id** – from TR.TXT; `~` = no teacher.
  6. **room_1 … room_12** – room codes from RR.TXT; `~` = no room.
  7. **numeric fields** – likely capacity, enrollment, or conflict/priority (e.g. `5 12 1` then many zeros).

- Each row = one **section** of a course in one **period**. Same course_id can appear in multiple rows (multiple sections, possibly different periods).

### 2.3 Student schedule (solver output) – SH.TXT

- **Delimiter**: tab.
- **Columns**:
  1. **student_id**
  2. **col2** – constant `2` (semester/term).
  3. **course_id**
  4. **one integer** – likely **period** (1–6) or **section count** for that course.
  5. **six integers** – section index or slot per time slot (1-based); **-1** = not scheduled in that slot.

- **Interpretation**: Each line = one course placement for one student. The six values likely correspond to six period slots (or A/B day slots); positive = section number in that slot, -1 = no class in that slot. Study halls (28xx) often have all -1 (floating).

- **Volume**: ~17,041 rows; multiple rows per student (one per course).

### 2.4 Teacher roster – TR.TXT

- **Format**: `teacher_id\tLast, First` (tab).
- **Special**: `999999	ZZZ, Save` likely end-of-file or placeholder.

### 2.5 Student directory – SD.TXT

- **Format**: `student_id\tName` (tab).
- Used to resolve student_id in requests and SH.TXT.

### 2.6 Room list – RR.TXT

- One room code per line (numeric like 115, 223, or text like AUDI, WCC, UNMC).
- First line `ZZZZZZZZZ` may be header/placeholder.

### 2.7 Student course requests – Requests.txt (and variants)

- **Format**: `student_id\tcourse_id` (tab), one request per line.
- A student appears on multiple lines for multiple course requests (full request list).
- **Order may matter** for priority (first = higher priority) in the original algorithm.

### 2.8 Students list – students.txt (SKEDFiles)

- **Format**: `Name\tstudent_id\t?\t?\tGender\tGradYear` (tabs).
- The two repeated columns (e.g. 2811, 2811) may be homeroom or building id.

---

## 3. ID Conventions (for your Python model)

- **course_id**: 4–5 digit int. 10xx–19xx = regular courses; 28xx = study hall; 29xx = support; 20xx = admin; 35xx/41xx/49xx = other.
- **student_id**: 5–6 digit int (some 7-digit).
- **teacher_id**: 4–5 digit int; 999999 = placeholder.
- **Rooms**: string (numeric or text).
- **Periods**: 1–6 (or 1–7) in CH and in the 6-slot fields in SH.

---

## 4. Inferred Algorithm (high level)

Without the actual executable, the flow is inferred from inputs and outputs:

1. **Load master data**
   - Courses from PRIOR.TXT.
   - Sections (and period, teacher, room) from CH.TXT.
   - Teachers (TR.TXT), rooms (RR.TXT), students (SD.TXT or students.txt).

2. **Load requests**
   - From Requests.txt: set of (student_id, course_id) pairs per student.

3. **Constraints (implied)**
   - No two sections in the same period for one student (no double-booking).
   - Section capacity (from CH.TXT numeric fields) not exceeded.
   - Teacher and room not double-booked in the same period (CH rows with same period, teacher, room).
   - Some courses may be “same period” (e.g. band) or “different period” (e.g. two semesters of same subject).

4. **Output**
   - SH.TXT: for each (student, course) one row with period and the six slot values (section/period assignment).

5. **Request handling**
   - Satisfy as many requests as possible; -1 in SH may mean “requested but not placed” or “study hall / no class in that slot”.
   - Order of requests in the file may be used as priority when resolving conflicts.

6. **Study hall / 28xx**
   - 28xx entries in SH often have the six values all -1; they may be placeholders for “free period” or “study hall” that don’t consume a period slot in the same way.

---

## 5. What to Build in Python

### 5.1 Data loaders

- **PRIOR**: parse CSV → `course_id, code, name, frequency, semester`.
- **CH**: parse TSV → sections with `course_id, period, section_number, teacher_id, rooms[], capacity?`.
- **TR, SD, RR**: simple id → name or code lists.
- **Requests**: list of `(student_id, course_id)`; optionally preserve order for priority.

### 5.2 Core structures

- **Course**: id, code, name, frequency, semester.
- **Section**: course_id, period, section_number, teacher_id, room(s), capacity, enrollment (to be filled).
- **Student**: id, name; list of requested course_ids (ordered if you use priority).
- **Assignment**: student_id, course_id, period, section_number (or equivalent to the “six slots” if you keep that model).

### 5.3 Solver (conceptual)

- **Variables**: assign each (student, request) to a section (or “no assignment”).
- **Constraints**:
  - At most one section per student per period.
  - Section enrollment ≤ capacity.
  - One teacher per section per period; one room per section per period (no teacher/room conflict).
- **Objective**: maximize requests satisfied (and optionally respect request order as tie-breaker or soft priority).

You can implement this with constraint programming (e.g. `python-constraint`, OR-Tools) or integer linear programming, or a custom greedy/heuristic that respects the same constraints.

### 5.4 Output

- Emit something equivalent to SH.TXT: one row per (student, course) with period and section (or your equivalent of the six slot columns).

---

## 6. Quick reference – column counts

| File    | Separator | Key columns |
|---------|-----------|-------------|
| PRIOR   | comma     | 5: course_id, code, name, frequency, semester |
| CH      | tab       | 30+: course_id, col2, period, section, teacher, 12 rooms, then numeric |
| SH      | tab       | 9: student_id, col2, course_id, 1 int, 6 ints (section/slot or -1) |
| TR      | tab       | 2: teacher_id, name |
| SD      | tab       | 2: student_id, name |
| RR      | line      | 1: room code |
| Requests| tab       | 2: student_id, course_id |

---

## 7. Suggested next steps

1. **Parse all files** in Python and validate: no duplicate (course_id, period, section) in CH; every course_id in SH and Requests appears in PRIOR; every teacher_id in CH appears in TR; every student_id in SH and Requests in SD/students.
2. **Infer period layout**: from CH, list (period, section) per course and confirm 1–6 (or 1–7) period range.
3. **Clarify the “six numbers”** in SH by spot-checking: pick a student with a full schedule and compare to CH sections for those courses to see if values are section numbers or period indices.
4. **Implement constraint model** (CP or ILP) with the structures above, then compare your output to SH.TXT on a small subset.
5. **Add request priority** (order in Requests.txt) if the original behavior suggests it.

If you want, the next step can be a minimal Python script that only **loads and prints** PRIOR, CH, Requests, and SH (and optionally TR, SD, RR) into clear structures so you can inspect them before writing the solver.
