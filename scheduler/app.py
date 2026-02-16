"""Simple web app: upload reqexport (tab-delimited), run scheduler, download CSV results."""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from scheduler.cli import load_capacity
from scheduler.engine import Scheduler
from scheduler.parsers import (
    load_courses_from_reqexport,
    load_requests_from_reqexport,
    load_students_from_reqexport,
)
from scheduler.reports import assignments_csv_string, conflicts_csv_string

app = FastAPI(title="Scheduler", description="Upload reqexport → get assignments & conflicts CSV")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the upload form and result area."""
    return _INDEX_HTML


@app.post("/api/schedule")
async def schedule(
    reqexport: UploadFile = File(..., description="Tab-delimited reqexport (Student Name, Student Number, Next Grade, ...)"),
    capacity: UploadFile = File(None, description="Optional: tab-delimited capacity file (class_code, capacity)"),
    default_capacity: int = Form(999, description="Default capacity per class when no capacity file"),
) -> JSONResponse:
    """Run scheduler on uploaded reqexport. Returns assignments_csv, conflicts_csv, and summary."""
    if not reqexport.filename or not reqexport.filename.lower().endswith((".txt", ".tsv", ".csv")):
        raise HTTPException(400, "Upload a tab-delimited file (e.g. .txt or .tsv)")

    reqexport_content = await reqexport.read()
    capacity_content = b""
    if capacity and capacity.filename:
        capacity_content = await capacity.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        reqexport_path = Path(tmpdir) / "reqexport.txt"
        reqexport_path.write_bytes(reqexport_content)

        students = load_students_from_reqexport(reqexport_path)
        requests = load_requests_from_reqexport(reqexport_path)
        courses = load_courses_from_reqexport(reqexport_path)

        if capacity_content.strip():
            capacity_path = Path(tmpdir) / "capacity.txt"
            capacity_path.write_bytes(capacity_content)
            capacity_by_class = load_capacity(capacity_path)
        else:
            capacity_by_class = {code: default_capacity for code in courses}

        scheduler = Scheduler(capacity_by_class=capacity_by_class)
        assignments, conflicts = scheduler.schedule(students, requests, courses)

        assignments_csv = assignments_csv_string(assignments, students, courses)
        conflicts_csv = conflicts_csv_string(conflicts, students)

    return JSONResponse(
        content={
            "assignments_csv": assignments_csv,
            "conflicts_csv": conflicts_csv,
            "summary": {
                "assignments": len(assignments),
                "conflicts": len(conflicts),
                "students": len(students),
                "courses": len(courses),
            },
        }
    )


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scheduler</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.5rem; }
    label { display: block; margin-top: 1rem; font-weight: 500; }
    input[type="file"], input[type="number"] { margin-top: 0.25rem; }
    button { margin-top: 1rem; padding: 0.5rem 1rem; background: #0d6efd; color: white; border: none; border-radius: 6px; cursor: pointer; }
    button:hover { background: #0b5ed7; }
    #result { margin-top: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; display: none; }
    #result.show { display: block; }
    #result summary { font-weight: 600; }
    #result a { display: inline-block; margin-right: 1rem; margin-top: 0.5rem; color: #0d6efd; }
    .error { color: #dc3545; }
  </style>
</head>
<body>
  <h1>Scheduler</h1>
  <p>Upload a tab-delimited reqexport file. You’ll get back assignments and conflicts as CSV.</p>
  <form id="form">
    <label for="reqexport">Reqexport file (required) *</label>
    <input type="file" id="reqexport" name="reqexport" accept=".txt,.tsv,.csv" required>
    <label for="capacity">Capacity file (optional)</label>
    <input type="file" id="capacity" name="capacity" accept=".txt,.tsv,.csv">
    <label for="default_capacity">Default capacity per class (if no capacity file)</label>
    <input type="number" id="default_capacity" name="default_capacity" value="999" min="1">
    <button type="submit">Run schedule</button>
  </form>
  <div id="result">
    <p id="summary"></p>
    <p><a id="dl-assignments" href="#" download="assignments.csv">Download assignments.csv</a>
       <a id="dl-conflicts" href="#" download="conflicts.csv">Download conflicts.csv</a></p>
  </div>
  <p id="error" class="error"></p>
  <script>
    const form = document.getElementById('form');
    const result = document.getElementById('result');
    const summary = document.getElementById('summary');
    const dlAssignments = document.getElementById('dl-assignments');
    const dlConflicts = document.getElementById('dl-conflicts');
    const errEl = document.getElementById('error');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errEl.textContent = '';
      result.classList.remove('show');
      const fd = new FormData();
      fd.append('reqexport', document.getElementById('reqexport').files[0]);
      const cap = document.getElementById('capacity').files[0];
      if (cap) fd.append('capacity', cap);
      fd.append('default_capacity', document.getElementById('default_capacity').value);
      try {
        const r = await fetch('/api/schedule', { method: 'POST', body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || r.statusText);
        const s = data.summary;
        summary.textContent = `${s.assignments} assignments, ${s.conflicts} conflicts (${s.students} students, ${s.courses} courses).`;
        dlAssignments.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(data.assignments_csv);
        dlConflicts.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(data.conflicts_csv);
        result.classList.add('show');
      } catch (err) {
        errEl.textContent = err.message || 'Request failed';
      }
    });
  </script>
</body>
</html>
"""
