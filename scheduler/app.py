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
  <title>WHS Scheduler</title>
  <style>
    :root {
      --blue: #003087;
      --gold: #FFC72C;
      --blue-dark: #002060;
      --blue-light: #e8eef7;
      --green: #198754;
      --red: #dc3545;
      --gray: #6c757d;
      --border: #dee2e6;
      --radius: 10px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #f4f6fb; min-height: 100vh; }

    /* Header */
    header {
      background: var(--blue);
      color: white;
      padding: 1.25rem 2rem;
      display: flex;
      align-items: center;
      gap: 1rem;
      border-bottom: 4px solid var(--gold);
    }
    header h1 { font-size: 1.3rem; font-weight: 700; letter-spacing: 0.01em; }
    header p { font-size: 0.8rem; opacity: 0.75; margin-top: 0.15rem; }
    .logo {
      width: 44px; height: 44px; background: var(--gold);
      border-radius: 50%; display: flex; align-items: center;
      justify-content: center; font-size: 1.3rem; flex-shrink: 0;
    }

    /* Main */
    main { max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }

    /* Card */
    .card {
      background: white; border-radius: var(--radius);
      border: 1px solid var(--border); padding: 1.75rem;
      margin-bottom: 1.25rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .card-title {
      font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--gray); margin-bottom: 1rem;
    }

    /* File inputs */
    .file-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 540px) { .file-grid { grid-template-columns: 1fr; } }
    .file-zone {
      border: 2px dashed var(--border); border-radius: var(--radius);
      padding: 1.25rem 1rem; text-align: center; cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
      position: relative;
    }
    .file-zone:hover { border-color: var(--blue); background: var(--blue-light); }
    .file-zone.has-file { border-color: var(--green); border-style: solid; background: #f0faf4; }
    .file-zone input[type=\"file\"] {
      position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
    }
    .file-icon { font-size: 1.75rem; margin-bottom: 0.4rem; }
    .file-label { font-size: 0.8rem; font-weight: 600; color: #333; }
    .file-hint { font-size: 0.72rem; color: var(--gray); margin-top: 0.2rem; }
    .file-name {
      font-size: 0.75rem; color: var(--green); font-weight: 600;
      margin-top: 0.35rem; word-break: break-all;
    }

    /* Button */
    .btn {
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.65rem 1.4rem; border: none; border-radius: 6px;
      font-size: 0.9rem; font-weight: 600; cursor: pointer;
      transition: opacity 0.15s, transform 0.1s;
    }
    .btn:hover { opacity: 0.88; }
    .btn:active { transform: scale(0.98); }
    .btn-primary { background: var(--blue); color: white; margin-top: 1.25rem; }
    .btn-primary:disabled { background: var(--gray); cursor: not-allowed; opacity: 1; }
    .btn-dl {
      background: var(--blue-light); color: var(--blue);
      font-size: 0.8rem; padding: 0.45rem 0.9rem;
      text-decoration: none; border: 1px solid #c5d3e8;
    }
    .btn-dl.primary-dl { background: var(--blue); color: white; border-color: var(--blue); }

    /* Spinner */
    .spinner {
      display: none; width: 18px; height: 18px;
      border: 2px solid rgba(255,255,255,0.4);
      border-top-color: white; border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .loading .spinner { display: inline-block; }
    .loading .btn-text { display: none; }

    /* Stats */
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.25rem; }
    @media (max-width: 540px) { .stats { grid-template-columns: repeat(2, 1fr); } }
    .stat {
      background: var(--blue-light); border-radius: 8px;
      padding: 0.9rem 0.75rem; text-align: center;
    }
    .stat-value { font-size: 1.6rem; font-weight: 700; color: var(--blue); line-height: 1; }
    .stat-label { font-size: 0.68rem; color: var(--gray); text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.3rem; }
    .stat.red .stat-value { color: var(--red); }
    .stat.red { background: #fdf0f1; }
    .stat.green .stat-value { color: var(--green); }
    .stat.green { background: #f0faf4; }

    /* Downloads */
    .downloads { display: flex; flex-wrap: wrap; gap: 0.5rem; }

    /* Error */
    .error-box {
      background: #fdf0f1; border: 1px solid #f5c2c7; border-radius: 8px;
      padding: 0.85rem 1rem; color: var(--red); font-size: 0.875rem;
      display: none; margin-top: 1rem;
    }
    .error-box.show { display: block; }

    #result { display: none; }
    #result.show { display: block; }
  </style>
</head>
<body>

<header>
  <div class=\"logo\">🏫</div>
  <div>
    <h1>WHS Scheduler</h1>
    <p>Westside High School — Section Placement Engine</p>
  </div>
</header>

<main>
  <div class=\"card\">
    <div class=\"card-title\">Upload Export Files</div>
    <div class=\"file-grid\">
      <div class=\"file-zone\" id=\"zone-requests\">
        <input type=\"file\" id=\"requests_export\" name=\"requests_export\" accept=\".txt,.tsv,.csv\" required>
        <div class=\"file-icon\">📋</div>
        <div class=\"file-label\">Schedule Requests</div>
        <div class=\"file-hint\">ScheduleRequests.export.txt</div>
        <div class=\"file-name\" id=\"name-requests\"></div>
      </div>
      <div class=\"file-zone\" id=\"zone-offerings\">
        <input type=\"file\" id=\"section_offerings\" name=\"section_offerings\" accept=\".txt,.tsv,.csv\" required>
        <div class=\"file-icon\">📅</div>
        <div class=\"file-label\">Section Offerings</div>
        <div class=\"file-hint\">Sem 1 sked export with phases.txt</div>
        <div class=\"file-name\" id=\"name-offerings\"></div>
      </div>
    </div>
    <button class=\"btn btn-primary\" id=\"run-btn\" type=\"button\" disabled>
      <span class=\"spinner\"></span>
      <span class=\"btn-text\">▶ Run Schedule</span>
    </button>
    <div class=\"error-box\" id=\"error-box\"></div>
  </div>

  <div class=\"card\" id=\"result\">
    <div class=\"card-title\">Results</div>
    <div class=\"stats\">
      <div class=\"stat green\">
        <div class=\"stat-value\" id=\"s-assignments\">—</div>
        <div class=\"stat-label\">Assigned</div>
      </div>
      <div class=\"stat red\">
        <div class=\"stat-value\" id=\"s-conflicts\">—</div>
        <div class=\"stat-label\">Conflicts</div>
      </div>
      <div class=\"stat\">
        <div class=\"stat-value\" id=\"s-dropped\">—</div>
        <div class=\"stat-label\">Dropped</div>
      </div>
      <div class=\"stat\">
        <div class=\"stat-value\" id=\"s-students\">—</div>
        <div class=\"stat-label\">Students</div>
      </div>
    </div>
    <div class=\"card-title\">Download Outputs</div>
    <div class=\"downloads\">
      <a class=\"btn btn-dl primary-dl\" id=\"dl-schedulecc\" download=\"schedulecc.txt\">⬇ schedulecc.txt</a>
      <a class=\"btn btn-dl\" id=\"dl-conflicts\" download=\"conflicts.txt\">⬇ conflicts.txt</a>
      <a class=\"btn btn-dl\" id=\"dl-dropped\" download=\"dropped_by_reason.txt\">⬇ dropped_by_reason.txt</a>
      <a class=\"btn btn-dl\" id=\"dl-assignments\" download=\"assignments.txt\">⬇ assignments.txt</a>
    </div>
  </div>
</main>

<script>
  const reqInput  = document.getElementById('requests_export');
  const offInput  = document.getElementById('section_offerings');
  const runBtn    = document.getElementById('run-btn');
  const errorBox  = document.getElementById('error-box');
  const result    = document.getElementById('result');

  function updateZone(input, zoneId, nameId) {
    const zone = document.getElementById(zoneId);
    const nameEl = document.getElementById(nameId);
    input.addEventListener('change', () => {
      if (input.files[0]) {
        zone.classList.add('has-file');
        nameEl.textContent = input.files[0].name;
      } else {
        zone.classList.remove('has-file');
        nameEl.textContent = '';
      }
      runBtn.disabled = !(reqInput.files[0] && offInput.files[0]);
    });
  }
  updateZone(reqInput, 'zone-requests', 'name-requests');
  updateZone(offInput, 'zone-offerings', 'name-offerings');

  function fmt(n) { return Number(n).toLocaleString(); }

  runBtn.addEventListener('click', async () => {
    errorBox.classList.remove('show');
    result.classList.remove('show');
    runBtn.classList.add('loading');
    runBtn.disabled = true;

    const fd = new FormData();
    fd.append('requests_export', reqInput.files[0]);
    fd.append('section_offerings', offInput.files[0]);

    try {
      const r = await fetch('/api/schedule', { method: 'POST', body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);

      const s = data.summary;
      document.getElementById('s-assignments').textContent = fmt(s.assignments);
      document.getElementById('s-conflicts').textContent   = fmt(s.conflicts);
      document.getElementById('s-dropped').textContent     = fmt(s.dropped);
      document.getElementById('s-students').textContent    = fmt(s.students);

      const enc = encodeURIComponent;
      document.getElementById('dl-schedulecc').href  = 'data:text/plain;charset=utf-8,' + enc(data.schedulecc_csv);
      document.getElementById('dl-dropped').href     = 'data:text/plain;charset=utf-8,' + enc(data.dropped_by_reason_csv);
      document.getElementById('dl-conflicts').href   = 'data:text/plain;charset=utf-8,' + enc(data.conflicts_csv);
      document.getElementById('dl-assignments').href = 'data:text/plain;charset=utf-8,' + enc(data.assignments_csv);

      result.classList.add('show');
    } catch (err) {
      errorBox.textContent = err.message || 'Request failed.';
      errorBox.classList.add('show');
    } finally {
      runBtn.classList.remove('loading');
      runBtn.disabled = false;
    }
  });
</script>
</body>
</html>
"""
