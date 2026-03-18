"""Simple web app: upload request + section-offering exports, download scheduling CSV outputs."""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from scheduler.engine import Scheduler
from scheduler.models import Assignment
from scheduler.parsers import (
    load_courses_from_requests_export,
    load_courses_from_section_offerings,
    load_requests_export,
    load_section_offerings,
    load_students_from_requests_export,
    reconcile_requests_to_offerings,
)
from scheduler.reports import (
    assignments_csv_string,
    conflicts_csv_string,
    write_dropped_by_reason_csv,
    write_schedulecc_csv_from_sections,
)

app = FastAPI(
    title="Scheduler",
    description="Upload ScheduleRequests + section offerings → get schedulecc + dropped-by-reason CSV",
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the upload form and result area."""
    return _INDEX_HTML


@app.post("/api/schedule")
async def schedule(
    requests_export: UploadFile = File(..., description="PowerSchool ScheduleRequests export"),
    section_offerings: UploadFile = File(..., description="PowerSchool section offerings export"),
) -> JSONResponse:
    """Run section-offerings scheduling and return CSV outputs."""
    for file in (requests_export, section_offerings):
        if not file.filename or not file.filename.lower().endswith((".txt", ".tsv", ".csv")):
            raise HTTPException(400, "Upload tab-delimited files (e.g. .txt or .tsv)")

    requests_content = await requests_export.read()
    offerings_content = await section_offerings.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        requests_path = Path(tmpdir) / "ScheduleRequests.export.txt"
        offerings_path = Path(tmpdir) / "section_offerings.txt"
        requests_path.write_bytes(requests_content)
        offerings_path.write_bytes(offerings_content)

        students = load_students_from_requests_export(requests_path)
        requests = load_requests_export(requests_path)
        courses = load_courses_from_requests_export(requests_path)
        courses.update(load_courses_from_section_offerings(offerings_path))

        offerings = load_section_offerings(offerings_path)
        requests, dropped_rows = reconcile_requests_to_offerings(requests, offerings)

        scheduler = Scheduler(capacity_by_class={})
        section_assignments, conflicts = scheduler.schedule_sections(students, requests, courses, offerings)

        class_assignments = [
            Assignment(student_id=a.student_id, class_code=a.class_code)
            for a in section_assignments
        ]
        assignments_csv = assignments_csv_string(class_assignments, students, courses)
        conflicts_csv = conflicts_csv_string(conflicts, students)

        schedulecc_path = Path(tmpdir) / "schedulecc.csv"
        dropped_path = Path(tmpdir) / "dropped_by_reason.csv"
        write_schedulecc_csv_from_sections(schedulecc_path, section_assignments, offerings)
        write_dropped_by_reason_csv(dropped_path, dropped_rows, students)
        schedulecc_csv = schedulecc_path.read_text(encoding="utf-8")
        dropped_csv = dropped_path.read_text(encoding="utf-8")

    return JSONResponse(
        content={
            "schedulecc_csv": schedulecc_csv,
            "dropped_by_reason_csv": dropped_csv,
            "assignments_csv": assignments_csv,
            "conflicts_csv": conflicts_csv,
            "summary": {
                "assignments": len(section_assignments),
                "conflicts": len(conflicts),
                "dropped": len(dropped_rows),
                "students": len(students),
                "courses": len(courses),
            },
        }
    )


_INDEX_HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Scheduler</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.5rem; }
    label { display: block; margin-top: 1rem; font-weight: 500; }
    input[type=\"file\"] { margin-top: 0.25rem; }
    button { margin-top: 1rem; padding: 0.5rem 1rem; background: #0d6efd; color: white; border: none; border-radius: 6px; cursor: pointer; }
    button:hover { background: #0b5ed7; }
    #result { margin-top: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; display: none; }
    #result.show { display: block; }
    #result a { display: inline-block; margin-right: 1rem; margin-top: 0.5rem; color: #0d6efd; }
    .error { color: #dc3545; }
  </style>
</head>
<body>
  <h1>Scheduler (Section-Offerings Mode)</h1>
  <p>Upload 2 tab-delimited files: ScheduleRequests export + Sem 1 section offerings export.</p>
  <form id=\"form\">
    <label for=\"requests_export\">ScheduleRequests export (required) *</label>
    <input type=\"file\" id=\"requests_export\" name=\"requests_export\" accept=\".txt,.tsv,.csv\" required>

    <label for=\"section_offerings\">Section offerings export (required) *</label>
    <input type=\"file\" id=\"section_offerings\" name=\"section_offerings\" accept=\".txt,.tsv,.csv\" required>

    <button type=\"submit\">Run schedule</button>
  </form>

  <div id=\"result\">
    <p id=\"summary\"></p>
    <p>
      <a id=\"dl-schedulecc\" href=\"#\" download=\"schedulecc.txt\">Download schedulecc.txt</a>
      <a id=\"dl-dropped\" href=\"#\" download=\"dropped_by_reason.txt\">Download dropped_by_reason.txt</a>
      <a id=\"dl-conflicts\" href=\"#\" download=\"conflicts.txt\">Download conflicts.txt</a>
      <a id=\"dl-assignments\" href=\"#\" download=\"assignments.txt\">Download assignments.txt</a>
    </p>
  </div>

  <p id=\"error\" class=\"error\"></p>

  <script>
    const form = document.getElementById('form');
    const result = document.getElementById('result');
    const summary = document.getElementById('summary');
    const dlSchedulecc = document.getElementById('dl-schedulecc');
    const dlDropped = document.getElementById('dl-dropped');
    const dlConflicts = document.getElementById('dl-conflicts');
    const dlAssignments = document.getElementById('dl-assignments');
    const errEl = document.getElementById('error');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errEl.textContent = '';
      result.classList.remove('show');

      const fd = new FormData();
      fd.append('requests_export', document.getElementById('requests_export').files[0]);
      fd.append('section_offerings', document.getElementById('section_offerings').files[0]);

      try {
        const r = await fetch('/api/schedule', { method: 'POST', body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || r.statusText);

        const s = data.summary;
        summary.textContent = `${s.assignments} assignments, ${s.conflicts} conflicts, ${s.dropped} dropped (${s.students} students, ${s.courses} courses).`;

        dlSchedulecc.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(data.schedulecc_csv);
        dlDropped.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(data.dropped_by_reason_csv);
        dlConflicts.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(data.conflicts_csv);
        dlAssignments.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(data.assignments_csv);

        result.classList.add('show');
      } catch (err) {
        errEl.textContent = err.message || 'Request failed';
      }
    });
  </script>
</body>
</html>
"""
