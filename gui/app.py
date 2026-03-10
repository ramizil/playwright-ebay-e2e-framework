"""
Test Runner Web GUI
===================

A lightweight Flask application that provides a browser-based interface
for triggering pytest test runs, streaming live output, and viewing
screenshots and Allure reports.

Start with:
    python gui/app.py

Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SCREENSHOTS_DIR = ROOT_DIR / "screenshots"
ALLURE_RESULTS_DIR = ROOT_DIR / "allure-results"
REPORTS_DIR = ROOT_DIR / "reports"

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ---------------------------------------------------------------------------
# In-memory state for the currently running test
# ---------------------------------------------------------------------------
_run_lock = threading.Lock()
_current_run: dict | None = None


def _load_scenarios() -> list[dict]:
    path = DATA_DIR / "search_data.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["test_scenarios"]


def _discover_tests() -> list[dict]:
    """Dynamically discover all test files and functions in ``tests/``.

    Returns a flat list with one entry per test file, each containing
    the file name, a display-friendly label, and the ``-k`` expression
    needed to run it.
    """
    tests_dir = ROOT_DIR / "tests"
    discovered: list[dict] = []

    for test_file in sorted(tests_dir.glob("test_*.py")):
        name = test_file.stem
        label = name.replace("test_", "").replace("_", " ").title()

        functions: list[str] = []
        with open(test_file, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("def test_"):
                    fn_name = stripped.split("(")[0].replace("def ", "")
                    functions.append(fn_name)

        discovered.append({
            "file": test_file.name,
            "name": name,
            "label": label,
            "functions": functions,
            "k_expr": name,
        })

    return discovered


def _load_config() -> dict:
    import yaml
    path = ROOT_DIR / "config" / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    """Return available browsers, scenarios, discovered tests, and settings."""
    scenarios = _load_scenarios()
    cfg = _load_config()
    tests = _discover_tests()
    return jsonify({
        "browsers": cfg.get("browsers", ["chromium"]),
        "scenarios": scenarios,
        "tests": tests,
        "headless": cfg.get("browser_options", {}).get("headless", True),
        "base_url": cfg.get("base_url", "https://www.ebay.com"),
    })


@app.route("/api/run", methods=["POST"])
def api_run():
    """Start a new test run. Returns immediately; logs stream via SSE."""
    global _current_run

    with _run_lock:
        if _current_run and _current_run.get("running"):
            return jsonify({"error": "A test run is already in progress"}), 409

    body = request.json or {}
    browser = body.get("browser", "chromium")
    scenarios = body.get("scenarios", [])
    headed = body.get("headed", False)
    workers = body.get("workers", 1)

    run_id = time.strftime("%Y%m%d_%H%M%S")

    test_filters = body.get("test_filters", [])

    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]
    cmd += [f"--alluredir=allure-results/run_{run_id}"]

    if workers > 1:
        cmd += [f"-n={workers}"]

    all_k_parts = []
    if scenarios:
        all_k_parts.extend(scenarios)
    if test_filters:
        all_k_parts.extend(test_filters)
    if all_k_parts:
        k_expr = " or ".join(all_k_parts)
        cmd += ["-k", k_expr]

    env = os.environ.copy()
    env["EBAY_BROWSER"] = browser
    env["EBAY_HEADLESS"] = "false" if headed else "true"
    env["EBAY_RUN_ID"] = run_id
    env["EBAY_LIVE_VIEW"] = "true"
    env["PYTHONUNBUFFERED"] = "1"

    log_queue: queue.Queue[str | None] = queue.Queue()

    run_state = {
        "running": True,
        "run_id": run_id,
        "browser": browser,
        "scenarios": scenarios,
        "headed": headed,
        "started_at": time.time(),
        "log_queue": log_queue,
        "exit_code": None,
    }

    def _run_process():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT_DIR),
                env=env,
                text=True,
                bufsize=1,
            )
            run_state["pid"] = proc.pid
            for line in proc.stdout:
                log_queue.put(line.rstrip("\n"))
            proc.wait()
            run_state["exit_code"] = proc.returncode
        except Exception as exc:
            log_queue.put(f"[ERROR] {exc}")
            run_state["exit_code"] = -1
        finally:
            run_state["running"] = False
            log_queue.put(None)

    with _run_lock:
        _current_run = run_state

    t = threading.Thread(target=_run_process, daemon=True)
    t.start()

    return jsonify({"status": "started", "run_id": run_id})


@app.route("/api/stream")
def api_stream():
    """Server-Sent Events endpoint for live log output."""
    def generate():
        if not _current_run:
            yield "data: {\"type\":\"error\",\"message\":\"No active run\"}\n\n"
            return

        q = _current_run["log_queue"]
        yield f"data: {json.dumps({'type': 'started', 'run_id': _current_run['run_id']})}\n\n"

        while True:
            try:
                line = q.get(timeout=30)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue

            if line is None:
                result = {
                    "type": "finished",
                    "exit_code": _current_run.get("exit_code"),
                    "run_id": _current_run["run_id"],
                    "duration": round(time.time() - _current_run["started_at"], 1),
                }
                yield f"data: {json.dumps(result)}\n\n"
                break

            yield f"data: {json.dumps({'type': 'log', 'line': line})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/status")
def api_status():
    """Return current run status."""
    if not _current_run:
        return jsonify({"running": False})
    return jsonify({
        "running": _current_run["running"],
        "run_id": _current_run["run_id"],
        "browser": _current_run["browser"],
        "exit_code": _current_run.get("exit_code"),
        "duration": round(time.time() - _current_run["started_at"], 1) if _current_run["running"] else None,
    })


@app.route("/api/screenshots")
def api_screenshots():
    """List recent screenshot files."""
    if not SCREENSHOTS_DIR.exists():
        return jsonify([])
    files = sorted(SCREENSHOTS_DIR.glob("*.png"), key=os.path.getmtime, reverse=True)
    return jsonify([{"name": f.name, "url": f"/screenshots/{f.name}"} for f in files[:30]])


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory(str(SCREENSHOTS_DIR), filename)


@app.route("/api/live-view")
def api_live_view():
    """Serve the latest live-view screenshot with cache-busting headers."""
    live_path = SCREENSHOTS_DIR / "_live_view.png"
    if not live_path.exists():
        return "", 204
    return send_from_directory(
        str(SCREENSHOTS_DIR),
        "_live_view.png",
        mimetype="image/png",
        max_age=0,
    )


@app.route("/api/runs")
def api_runs():
    """List available Allure result folders."""
    if not ALLURE_RESULTS_DIR.exists():
        return jsonify([])
    runs = []
    for d in sorted(ALLURE_RESULTS_DIR.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("run_"):
            runs.append({
                "id": d.name.replace("run_", ""),
                "path": str(d),
                "files": len(list(d.glob("*"))),
            })
    return jsonify(runs[:20])


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Kill the running test process."""
    if not _current_run or not _current_run.get("running"):
        return jsonify({"error": "No active run"}), 404
    pid = _current_run.get("pid")
    if pid:
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            return jsonify({"status": "stopped", "pid": pid})
        except OSError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No PID available"}), 500


@app.route("/api/reports")
def api_reports():
    """List generated HTML report files (newest first).

    Scans both the top-level ``reports/`` directory and per-run sub-folders
    (``reports/run_*/``) so it works for both old flat reports and new
    per-run organised reports.
    """
    if not REPORTS_DIR.exists():
        return jsonify([])
    files = sorted(REPORTS_DIR.rglob("*.html"), key=os.path.getmtime, reverse=True)
    return jsonify([
        {"name": f.stem, "filename": f.name,
         "url": f"/reports/{f.relative_to(REPORTS_DIR).as_posix()}",
         "run": f.parent.name if f.parent != REPORTS_DIR else "",
         "size": f.stat().st_size, "mtime": os.path.getmtime(f)}
        for f in files[:50]
    ])


@app.route("/reports/<path:filename>")
def serve_report(filename):
    """Serve an HTML report file (supports nested run_* sub-folders)."""
    return send_from_directory(str(REPORTS_DIR), filename)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n  Test Runner GUI: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
