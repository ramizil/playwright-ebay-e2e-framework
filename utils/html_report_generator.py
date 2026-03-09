"""
HTML Report Generator
=====================

Generates self-contained, single-file HTML test execution reports that
embed screenshots as base64.  Reports use a vertical collapsible tree
layout with a futuristic glassmorphism design.

Usage::

    from utils.html_report_generator import generate_scenario_report, generate_run_summary

    generate_scenario_report(scenario_record, output_dir="reports")
    generate_run_summary(all_records, output_dir="reports")
"""

from __future__ import annotations

import base64
import html as html_mod
import time
from pathlib import Path
from typing import List, Optional

from utils.step_collector import ScenarioRecord, StepRecord, SubStep


REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _screenshot_b64(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    try:
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def _fmt_duration(seconds: float) -> str:
    if seconds < 0.01:
        return "< 10ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m {secs:.0f}s"


def _status_class(status: str) -> str:
    return {"pass": "pass", "fail": "fail", "skip": "skip", "warn": "warn", "retry": "retry"}.get(status.lower(), "")


def _action_icon(action: str) -> str:
    icons = {
        "navigate": "&#xe157;",
        "click": "&#xe5ca;",
        "fill": "&#xe3c9;",
        "type_text": "&#xe312;",
        "press_key": "&#xe31b;",
        "find_element": "&#xe8b6;",
        "get_text": "&#xe873;",
        "screenshot": "&#xe3b0;",
        "wait": "&#xe425;",
        "scroll": "&#xe5db;",
        "dismiss_dialogs": "&#xe5cd;",
        "select_option": "&#xe876;",
        "retry": "&#xe042;",
    }
    return icons.get(action, "&#xe836;")


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons+Round');

:root {
    --bg: #06080d;
    --bg2: #0c0f18;
    --glass: rgba(16, 20, 32, .72);
    --glass2: rgba(20, 26, 42, .55);
    --border: rgba(255,255,255,.06);
    --border-glow: rgba(99,179,255,.15);
    --text: #e8ecf4;
    --text2: #7b8498;
    --text3: #4a5168;
    --accent: #63b3ff;
    --accent2: #a78bfa;
    --green: #34d399;
    --green-glow: rgba(52,211,153,.25);
    --red: #f87171;
    --red-glow: rgba(248,113,113,.25);
    --orange: #fbbf24;
    --orange-glow: rgba(251,191,36,.2);
    --yellow: #fde68a;
    --cyan: #22d3ee;
    --gradient1: linear-gradient(135deg, #63b3ff 0%, #a78bfa 50%, #f472b6 100%);
    --gradient-green: linear-gradient(135deg, #34d399, #22d3ee);
    --gradient-red: linear-gradient(135deg, #f87171, #fb923c);
    --gradient-warn: linear-gradient(135deg, #fbbf24, #fb923c);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    min-height: 100vh; overflow-x: hidden;
}
body::before {
    content: ''; position: fixed; inset: 0; z-index: -1;
    background:
        radial-gradient(ellipse 80% 60% at 20% 10%, rgba(99,179,255,.07) 0%, transparent 60%),
        radial-gradient(ellipse 60% 50% at 80% 80%, rgba(167,139,250,.05) 0%, transparent 60%),
        radial-gradient(ellipse 50% 40% at 50% 50%, rgba(244,114,182,.03) 0%, transparent 60%);
}

.mi { font-family: 'Material Icons Round'; font-size: 18px; font-style: normal; vertical-align: middle; }

/* ── Animated background mesh ───────────────────────────── */
.bg-mesh {
    position: fixed; inset: 0; z-index: -1; opacity: .3;
    background-image:
        linear-gradient(rgba(99,179,255,.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(99,179,255,.03) 1px, transparent 1px);
    background-size: 60px 60px;
}

/* ── Header ─────────────────────────────────────────────── */
.header {
    position: sticky; top: 0; z-index: 100;
    background: rgba(6,8,13,.85); backdrop-filter: blur(20px) saturate(1.4);
    -webkit-backdrop-filter: blur(20px) saturate(1.4);
    border-bottom: 1px solid var(--border);
    padding: 20px 32px 18px;
}
.header-inner { max-width: 1200px; margin: 0 auto; }
.header-top { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }

.result-ring {
    width: 76px; height: 76px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 800; letter-spacing: .5px;
    position: relative;
}
.result-ring::before {
    content: ''; position: absolute; inset: -3px; border-radius: 50%;
    padding: 3px; mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask-composite: exclude; -webkit-mask-composite: xor;
}
.result-ring.pass { color: var(--green); }
.result-ring.pass::before { background: var(--gradient-green); }
.result-ring.fail { color: var(--red); }
.result-ring.fail::before { background: var(--gradient-red); }
.result-ring.skip { color: var(--orange); }
.result-ring.skip::before { background: var(--gradient-warn); }
.result-ring .glow {
    position: absolute; inset: -8px; border-radius: 50%; z-index: -1;
    filter: blur(16px); opacity: .5;
}
.result-ring.pass .glow { background: var(--green); }
.result-ring.fail .glow { background: var(--red); }
.result-ring.skip .glow { background: var(--orange); }

.header h1 {
    font-size: 22px; font-weight: 700; letter-spacing: -.3px;
    background: var(--gradient1); -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; background-clip: text;
}
.header .sub { color: var(--text2); font-size: 12px; margin-top: 2px; font-weight: 400; }

.stats-bar {
    display: flex; gap: 6px; margin-top: 16px; flex-wrap: wrap;
}
.stat-chip {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 10px;
    background: var(--glass); border: 1px solid var(--border);
    font-size: 12px; font-weight: 500; color: var(--text2);
    backdrop-filter: blur(8px);
    transition: border-color .2s, transform .15s;
}
.stat-chip:hover { transform: translateY(-1px); border-color: var(--border-glow); }
.stat-chip .sv { font-weight: 700; font-size: 14px; font-variant-numeric: tabular-nums; }
.stat-chip.pass .sv { color: var(--green); }
.stat-chip.fail .sv { color: var(--red); }
.stat-chip.warn .sv { color: var(--orange); }
.stat-chip.retry .sv { color: #c084fc; }
.stat-chip.total .sv { color: var(--accent); }
.stat-chip.dur .sv { color: var(--accent2); }

.toolbar {
    margin-left: auto; display: flex; gap: 6px;
}
.toolbar button {
    padding: 6px 14px; border-radius: 8px; font-size: 11px;
    font-weight: 600; cursor: pointer; letter-spacing: .3px;
    border: 1px solid var(--border); color: var(--text2);
    background: var(--glass); backdrop-filter: blur(8px);
    transition: all .2s;
}
.toolbar button:hover {
    border-color: var(--accent); color: var(--accent);
    box-shadow: 0 0 12px rgba(99,179,255,.1);
}

/* ── Content wrapper ────────────────────────────────────── */
.content { max-width: 1200px; margin: 0 auto; padding: 24px 32px 60px; }

/* ── Scenario banner ────────────────────────────────────── */
.scenario-banner {
    background: var(--glass); backdrop-filter: blur(12px);
    border: 1px solid var(--border); border-radius: 16px;
    padding: 20px 24px; margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between;
    position: relative; overflow: hidden;
}
.scenario-banner::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
}
.scenario-banner.pass::before { background: var(--gradient-green); }
.scenario-banner.fail::before { background: var(--gradient-red); }
.scenario-banner.skip::before { background: var(--gradient-warn); }

.scenario-banner .name {
    font-size: 18px; font-weight: 700; letter-spacing: -.2px;
}
.scenario-banner .meta { color: var(--text2); font-size: 12px; margin-top: 4px; }
.badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 5px 16px; border-radius: 20px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px;
}
.badge.pass { background: rgba(52,211,153,.12); color: var(--green); border: 1px solid rgba(52,211,153,.25); }
.badge.fail { background: rgba(248,113,113,.12); color: var(--red); border: 1px solid rgba(248,113,113,.25); }
.badge.skip { background: rgba(251,191,36,.12); color: var(--orange); border: 1px solid rgba(251,191,36,.25); }
.badge.warn { background: rgba(251,191,36,.12); color: var(--orange); border: 1px solid rgba(251,191,36,.25); }

/* ── Info grid ──────────────────────────────────────────── */
.info-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 10px; margin-bottom: 24px;
}
.info-box {
    background: var(--glass); backdrop-filter: blur(10px);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 18px; transition: border-color .2s, transform .2s;
}
.info-box:hover { border-color: var(--border-glow); transform: translateY(-2px); }
.info-box .lbl {
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px;
    color: var(--text3); font-weight: 600;
}
.info-box .val { font-size: 16px; font-weight: 700; margin-top: 4px; }

/* ── Flow Timeline ──────────────────────────────────────── */
.flow-title {
    font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;
    color: var(--text3); margin-bottom: 16px; padding-left: 4px;
}

.timeline { position: relative; padding-left: 36px; }
.timeline::before {
    content: ''; position: absolute; left: 15px; top: 8px; bottom: 8px;
    width: 2px; border-radius: 1px;
    background: linear-gradient(180deg, var(--accent) 0%, var(--accent2) 50%, rgba(99,179,255,.15) 100%);
}

.step-node {
    position: relative; margin-bottom: 8px;
    animation: fadeSlideIn .35s ease-out both;
}
@keyframes fadeSlideIn { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }

.step-marker {
    position: absolute; left: -36px; top: 14px;
    width: 32px; height: 32px; border-radius: 50%; z-index: 2;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800;
    border: 2px solid var(--border);
    background: var(--bg2);
    transition: all .25s;
}
.step-marker.pass { border-color: var(--green); color: var(--green); box-shadow: 0 0 10px var(--green-glow); }
.step-marker.fail { border-color: var(--red); color: var(--red); box-shadow: 0 0 10px var(--red-glow); }
.step-marker.skip { border-color: var(--orange); color: var(--orange); }
.step-marker.warn { border-color: var(--orange); color: var(--orange); box-shadow: 0 0 10px var(--orange-glow); }

.step-card {
    background: var(--glass); backdrop-filter: blur(10px);
    border: 1px solid var(--border); border-radius: 12px;
    overflow: hidden; transition: border-color .25s, box-shadow .25s;
}
.step-card:hover { border-color: var(--border-glow); box-shadow: 0 4px 24px rgba(0,0,0,.3); }

.step-head {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; cursor: pointer; user-select: none;
    transition: background .15s;
}
.step-head:hover { background: rgba(99,179,255,.04); }

.step-arrow {
    width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
    border-radius: 6px; background: rgba(99,179,255,.08);
    color: var(--text2); font-size: 14px;
    transition: transform .25s, background .2s;
}
.step-arrow.open { transform: rotate(90deg); background: rgba(99,179,255,.15); }
.step-arrow.empty { background: transparent; }

.step-label { font-size: 14px; font-weight: 600; flex: 1; }
.step-label .sub-count { color: var(--text3); font-size: 11px; font-weight: 400; margin-left: 6px; }
.step-method {
    font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
    font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 6px;
    background: rgba(99,179,255,.08); color: var(--accent);
}
.step-badge {
    padding: 3px 10px; border-radius: 6px; font-size: 10px;
    font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
}
.step-badge.pass { background: rgba(52,211,153,.1); color: var(--green); }
.step-badge.fail { background: rgba(248,113,113,.1); color: var(--red); }
.step-badge.skip { background: rgba(251,191,36,.1); color: var(--orange); }
.step-badge.warn { background: rgba(251,191,36,.1); color: var(--orange); }
.step-dur { color: var(--text3); font-size: 11px; font-variant-numeric: tabular-nums; min-width: 48px; text-align: right; }
.step-time { color: var(--text3); font-size: 11px; min-width: 52px; text-align: right; }

/* ── Step screenshot ────────────────────────────────────── */
.step-screenshot-wrap { padding: 8px 16px 12px; }
.step-screenshot {
    max-width: 280px; max-height: 170px; border-radius: 10px;
    border: 1px solid var(--border); cursor: pointer;
    transition: transform .25s, box-shadow .25s, border-color .25s;
}
.step-screenshot:hover {
    transform: scale(1.03); border-color: var(--accent);
    box-shadow: 0 8px 32px rgba(99,179,255,.15);
}

/* ── Sub-steps ──────────────────────────────────────────── */
.sub-steps {
    display: none; border-top: 1px solid var(--border);
    background: rgba(6,8,13,.4);
}
.sub-steps.open { display: block; }

.sub-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 16px 8px 20px; font-size: 12px;
    border-bottom: 1px solid rgba(255,255,255,.03);
    transition: background .15s;
}
.sub-row:last-child { border-bottom: none; }
.sub-row:hover { background: rgba(99,179,255,.03); }

.sub-icon {
    width: 26px; height: 26px; border-radius: 6px; display: flex;
    align-items: center; justify-content: center; flex-shrink: 0;
    background: rgba(99,179,255,.06); color: var(--accent);
    font-size: 15px;
}
.sub-action {
    font-family: 'JetBrains Mono', monospace; font-weight: 600;
    color: var(--accent); min-width: 100px; font-size: 11px;
}
.sub-target { color: var(--text); flex: 1; word-break: break-word; }
.sub-detail { color: var(--text2); font-style: italic; font-size: 11px; }
.sub-dur { color: var(--text3); min-width: 48px; text-align: right; font-variant-numeric: tabular-nums; }

.sub-row.fail .sub-icon { background: rgba(248,113,113,.1); color: var(--red); }
.sub-row.fail .sub-action { color: var(--red); }
.sub-row.warn .sub-icon { background: rgba(251,191,36,.1); color: var(--orange); }
.sub-row.warn .sub-action { color: var(--orange); }
.sub-row.warn { background: rgba(251,191,36,.03); }
.sub-row.retry .sub-icon { background: rgba(168,85,247,.12); color: #c084fc; }
.sub-row.retry .sub-action { color: #c084fc; }
.sub-row.retry { background: rgba(168,85,247,.03); }
.retry-tag {
  display: inline-block; font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .5px; background: rgba(168,85,247,.12); color: #c084fc;
  border: 1px solid rgba(168,85,247,.25); border-radius: 4px; padding: 1px 6px;
  margin-left: 6px; vertical-align: middle;
}

.optional-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
    background: rgba(251,191,36,.1); color: var(--orange);
    border: 1px solid rgba(251,191,36,.2); margin-left: 8px;
}

.sub-screenshot {
    max-width: 120px; max-height: 80px; border-radius: 6px;
    border: 1px solid var(--border); cursor: pointer; margin-top: 4px;
    transition: transform .2s, border-color .2s;
}
.sub-screenshot:hover { transform: scale(1.06); border-color: var(--accent); }

/* ── Error box ──────────────────────────────────────────── */
.error-box {
    background: rgba(248,113,113,.06); border: 1px solid rgba(248,113,113,.2);
    border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;
    font-family: 'JetBrains Mono', monospace; font-size: 12px;
    color: #fca5a5; white-space: pre-wrap; word-break: break-word;
    max-height: 300px; overflow-y: auto;
    backdrop-filter: blur(8px);
}

/* ── Scenario detail panels (description / manual steps / expected) ── */
.scenario-detail {
    background: var(--glass); backdrop-filter: blur(10px);
    border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 22px; margin-bottom: 16px;
    transition: border-color .2s, transform .15s;
}
.scenario-detail:hover { border-color: var(--border-glow); transform: translateY(-1px); }
.scenario-detail .detail-header {
    display: flex; align-items: center; gap: 8px;
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px;
    color: var(--text3); font-weight: 700; margin-bottom: 10px;
}
.scenario-detail .detail-header .mi { font-size: 16px; color: var(--accent); }
.scenario-detail .detail-body {
    font-size: 13px; color: var(--text1); line-height: 1.65;
}
.scenario-detail ol {
    margin: 0; padding-left: 22px; counter-reset: step-counter;
    list-style: none;
}
.scenario-detail ol li {
    counter-increment: step-counter; position: relative;
    padding: 6px 0 6px 8px; border-left: 2px solid var(--border);
    margin-left: 6px;
}
.scenario-detail ol li::before {
    content: counter(step-counter);
    position: absolute; left: -16px; top: 5px;
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--glass); border: 1px solid var(--border);
    font-size: 10px; font-weight: 700; color: var(--accent);
    display: flex; align-items: center; justify-content: center;
}
.scenario-detail ol li:last-child { border-left-color: transparent; }
.scenario-detail .expected-text {
    background: rgba(52,211,153,.05); border: 1px solid rgba(52,211,153,.15);
    border-radius: 8px; padding: 10px 14px; font-size: 13px;
    color: var(--green); line-height: 1.5;
}
.scenario-panels { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
@media (max-width: 768px) { .scenario-panels { grid-template-columns: 1fr; } }

/* ── Lightbox ───────────────────────────────────────────── */
.lightbox {
    display: none; position: fixed; inset: 0; z-index: 9999;
    background: rgba(6,8,13,.95); backdrop-filter: blur(20px);
    align-items: center; justify-content: center; cursor: pointer;
}
.lightbox.active { display: flex; }
.lightbox img {
    max-width: 94vw; max-height: 94vh; border-radius: 12px;
    box-shadow: 0 20px 80px rgba(0,0,0,.6);
    animation: lbZoom .25s ease-out;
}
@keyframes lbZoom { from { transform: scale(.92); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.lightbox .close-btn {
    position: absolute; top: 20px; right: 24px;
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--glass); border: 1px solid var(--border);
    color: var(--text); font-size: 20px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
}

/* ── Footer ─────────────────────────────────────────────── */
.footer {
    text-align: center; padding: 24px; color: var(--text3);
    font-size: 11px; border-top: 1px solid var(--border);
    margin-top: 40px; letter-spacing: .3px;
}
.footer a { color: var(--accent); text-decoration: none; }

/* ── Progress bar ───────────────────────────────────────── */
.progress-bar {
    height: 4px; border-radius: 2px; background: rgba(255,255,255,.05);
    margin-top: 12px; overflow: hidden;
}
.progress-fill {
    height: 100%; border-radius: 2px;
    transition: width .6s ease-out;
}
.progress-fill.pass { background: var(--gradient-green); }
.progress-fill.fail { background: var(--gradient-red); }

/* ── Scrollbar ──────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--text3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text2); }

@media (max-width: 768px) {
    .header { padding: 16px; }
    .content { padding: 16px; }
    .info-grid { grid-template-columns: repeat(2, 1fr); }
    .step-method { display: none; }
    .step-time { display: none; }
}

@media print {
    body { background: #fff; color: #111; }
    body::before { display: none; }
    .bg-mesh { display: none; }
    .header { background: #f5f5f5 !important; backdrop-filter: none; position: static; }
    .step-card { background: #fafafa; border-color: #ddd; backdrop-filter: none; }
    .sub-steps { display: block !important; }
    .result-ring .glow { display: none; }
}
"""

# ---------------------------------------------------------------------------
# JS
# ---------------------------------------------------------------------------

_JS = r"""
function toggle(id) {
    var el = document.getElementById('sub-' + id);
    var ar = document.getElementById('arr-' + id);
    if (!el) return;
    el.classList.toggle('open');
    if (ar) ar.classList.toggle('open');
}

function openLB(src) {
    document.getElementById('lb-img').src = src;
    document.getElementById('lightbox').classList.add('active');
    document.body.style.overflow = 'hidden';
}
function closeLB() {
    document.getElementById('lightbox').classList.remove('active');
    document.body.style.overflow = '';
}
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeLB(); });

function expandAll() {
    document.querySelectorAll('.sub-steps').forEach(function(el) { el.classList.add('open'); });
    document.querySelectorAll('.step-arrow').forEach(function(el) { if (!el.classList.contains('empty')) el.classList.add('open'); });
}
function collapseAll() {
    document.querySelectorAll('.sub-steps').forEach(function(el) { el.classList.remove('open'); });
    document.querySelectorAll('.step-arrow').forEach(function(el) { el.classList.remove('open'); });
}

document.addEventListener('DOMContentLoaded', function() {
    var nodes = document.querySelectorAll('.step-node');
    nodes.forEach(function(n, i) { n.style.animationDelay = (i * 0.06) + 's'; });
});
"""


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------

def _build_sub_steps_html(subs: List[SubStep], step_id: str) -> str:
    if not subs:
        return ""
    rows = []
    for s in subs:
        cls = _status_class(s.status)
        icon = _action_icon(s.action)
        dur = _fmt_duration(s.duration) if s.duration > 0 else ""
        detail = f' <span class="sub-detail">{html_mod.escape(s.detail)}</span>' if s.detail else ""
        optional_tag = '<span class="optional-tag">optional</span>' if s.status.lower() == "warn" else ""
        retry_tag = '<span class="retry-tag">retry</span>' if s.status.lower() == "retry" else ""
        screenshot_html = ""
        if s.screenshot_path:
            b64 = _screenshot_b64(s.screenshot_path)
            if b64:
                screenshot_html = (
                    f'<br/><img class="sub-screenshot" src="{b64}" '
                    f'onclick="event.stopPropagation();openLB(this.src)" alt="screenshot"/>'
                )
        rows.append(
            f'<div class="sub-row {cls}">'
            f'  <span class="sub-icon"><span class="mi">{icon}</span></span>'
            f'  <span class="sub-action">{html_mod.escape(s.action)}</span>'
            f'  <span class="sub-target">{html_mod.escape(s.target)}{optional_tag}{retry_tag}{detail}{screenshot_html}</span>'
            f'  <span class="sub-dur">{dur}</span>'
            f'</div>'
        )
    return f'<div id="sub-{step_id}" class="sub-steps">\n' + "\n".join(rows) + '\n</div>'


def _build_step_node(step: StepRecord, step_id: str, step_num: int) -> str:
    cls = _status_class(step.status)
    dur = _fmt_duration(step.duration) if step.duration > 0 else ""
    has_subs = len(step.sub_steps) > 0
    arrow_cls = "" if has_subs else " empty"
    arrow = f'<div id="arr-{step_id}" class="step-arrow{arrow_cls}"><span class="mi" style="font-size:14px;">&#xe5cc;</span></div>'
    onclick = f'onclick="toggle(\'{step_id}\')"' if has_subs else ""
    sub_count = f'<span class="sub-count">{len(step.sub_steps)} actions</span>' if has_subs else ""

    screenshot_html = ""
    if step.screenshot_path:
        b64 = _screenshot_b64(step.screenshot_path)
        if b64:
            screenshot_html = (
                f'<div class="step-screenshot-wrap">'
                f'<img class="step-screenshot" src="{b64}" '
                f'onclick="event.stopPropagation();openLB(this.src)" alt="{html_mod.escape(step.name)}"/>'
                f'</div>'
            )

    subs_html = _build_sub_steps_html(step.sub_steps, step_id)

    return f"""
    <div class="step-node">
        <div class="step-marker {cls}">{step_num}</div>
        <div class="step-card">
            <div class="step-head" {onclick}>
                {arrow}
                <span class="step-label">{html_mod.escape(step.name)}{sub_count}</span>
                <span class="step-method">{html_mod.escape(step.method)}</span>
                <span class="step-badge {cls}">{step.status.upper()}</span>
                <span class="step-dur">{dur}</span>
                <span class="step-time">{step.timestamp}</span>
            </div>
            {screenshot_html}
            {subs_html}
        </div>
    </div>"""


def _build_scenario_html(rec: ScenarioRecord, prefix: str = "s0") -> str:
    duration = rec.finished_at - rec.started_at if rec.finished_at else 0
    n_pass = sum(1 for s in rec.steps if s.status.lower() == "pass")
    n_fail = sum(1 for s in rec.steps if s.status.lower() == "fail")
    n_warn = sum(1 for s in rec.steps if s.status.lower() == "warn")
    total_subs = sum(len(s.sub_steps) for s in rec.steps)
    cls = _status_class(rec.status)

    banner = f"""
    <div class="scenario-banner {cls}">
        <div>
            <div class="name">{html_mod.escape(rec.id)}</div>
            <div class="meta">
                {html_mod.escape(rec.query)} &middot; Max ${rec.max_price:.2f} &middot;
                {_fmt_duration(duration)} &middot;
                {len(rec.steps)} steps &middot; {total_subs} actions
            </div>
        </div>
        <span class="badge {cls}">{rec.status.upper()}</span>
    </div>
    """

    info_grid = f"""
    <div class="info-grid">
        <div class="info-box"><div class="lbl">Search Query</div><div class="val">{html_mod.escape(rec.query or 'N/A')}</div></div>
        <div class="info-box"><div class="lbl">Max Price</div><div class="val">${rec.max_price:.2f}</div></div>
        <div class="info-box"><div class="lbl">Browser</div><div class="val">{html_mod.escape(rec.browser or 'chromium')}</div></div>
        <div class="info-box"><div class="lbl">Items Found</div><div class="val">{rec.items_found}</div></div>
        <div class="info-box"><div class="lbl">Items Added</div><div class="val">{rec.items_added}</div></div>
        <div class="info-box"><div class="lbl">Duration</div><div class="val">{_fmt_duration(duration)}</div></div>
    </div>
    """

    detail_panels = ""
    has_desc = bool(rec.description)
    has_manual = bool(rec.manual_steps)
    has_expected = bool(rec.expected_results)

    if has_desc or has_manual or has_expected:
        desc_html = ""
        if has_desc:
            desc_html = f"""
            <div class="scenario-detail">
                <div class="detail-header"><span class="mi">&#xe88e;</span> Description</div>
                <div class="detail-body">{html_mod.escape(rec.description)}</div>
            </div>"""

        manual_html = ""
        if has_manual:
            li_items = "".join(f"<li>{html_mod.escape(s)}</li>" for s in rec.manual_steps)
            manual_html = f"""
            <div class="scenario-detail">
                <div class="detail-header"><span class="mi">&#xe8f4;</span> Steps to Reproduce (Manual)</div>
                <div class="detail-body"><ol>{li_items}</ol></div>
            </div>"""

        expected_html = ""
        if has_expected:
            expected_html = f"""
            <div class="scenario-detail">
                <div class="detail-header"><span class="mi">&#xe86c;</span> Expected Results</div>
                <div class="detail-body"><div class="expected-text">{html_mod.escape(rec.expected_results)}</div></div>
            </div>"""

        if has_manual and has_expected:
            detail_panels = f'{desc_html}<div class="scenario-panels">{manual_html}{expected_html}</div>'
        else:
            detail_panels = desc_html + manual_html + expected_html

    error_html = ""
    if rec.error_message:
        error_html = f'<div class="error-box">{html_mod.escape(rec.error_message)}</div>'

    steps_html = "\n".join(
        _build_step_node(step, f"{prefix}_{i}", i + 1)
        for i, step in enumerate(rec.steps)
    )

    total = max(len(rec.steps), 1)
    pct = round(n_pass / total * 100)
    bar_cls = "pass" if n_fail == 0 else "fail"

    return (
        banner + info_grid + detail_panels + error_html
        + f'<div class="flow-title">Execution Flow</div>'
        + f'<div class="progress-bar"><div class="progress-fill {bar_cls}" style="width:{pct}%;"></div></div>'
        + f'<div style="height:16px;"></div>'
        + f'<div class="timeline">\n{steps_html}\n</div>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_scenario_report(
    record: ScenarioRecord,
    output_dir: Optional[str] = None,
) -> str:
    """Generate a single-scenario HTML report file."""
    out = Path(output_dir) if output_dir else REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{record.id}_{timestamp}.html"
    filepath = out / filename

    duration = record.finished_at - record.started_at if record.finished_at else 0
    n_pass = sum(1 for s in record.steps if s.status.lower() == "pass")
    n_fail = sum(1 for s in record.steps if s.status.lower() == "fail")
    n_skip = sum(1 for s in record.steps if s.status.lower() == "skip")
    total_subs = sum(len(s.sub_steps) for s in record.steps)
    n_warn_subs = sum(
        sum(1 for sub in s.sub_steps if sub.status.lower() == "warn")
        for s in record.steps
    )
    n_retry_subs = sum(
        sum(1 for sub in s.sub_steps if sub.status.lower() == "retry")
        for s in record.steps
    )

    scenario_passed = record.status.lower() == "pass"
    scenario_failed = record.status.lower() == "fail"
    scenario_skipped = record.status.lower() == "skip"

    if scenario_passed:
        ring_cls = "pass"
        ring_label = "PASS"
    elif scenario_failed:
        ring_cls = "fail"
        ring_label = "FAIL"
    elif scenario_skipped:
        ring_cls = "skip"
        ring_label = "SKIP"
    else:
        ring_cls = ""
        ring_label = record.status.upper()

    started_str = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(record.started_at)) if record.started_at else "N/A"

    body_html = _build_scenario_html(record, "s0")

    filepath.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Test Report \u2014 {html_mod.escape(record.id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="bg-mesh"></div>

<div class="header">
  <div class="header-inner">
    <div class="header-top">
        <div class="result-ring {ring_cls}">
            <div class="glow"></div>
            {ring_label}
        </div>
        <div>
            <h1>eBay E2E Test Report</h1>
            <div class="sub">{started_str} &middot; {html_mod.escape(record.id)} &middot; {len(record.steps)} steps &middot; {total_subs} browser actions</div>
        </div>
        <div class="toolbar">
            <button onclick="expandAll()">Expand All</button>
            <button onclick="collapseAll()">Collapse All</button>
        </div>
    </div>
    <div class="stats-bar">
        <div class="stat-chip {ring_cls}"><span class="sv">{record.status.upper()}</span> Result</div>
        <div class="stat-chip total"><span class="sv">{len(record.steps)}</span> Steps</div>
        <div class="stat-chip pass"><span class="sv">{n_pass}</span> Passed</div>
        <div class="stat-chip fail"><span class="sv">{n_fail}</span> Failed</div>
        {"" if n_skip == 0 else f'<div class="stat-chip"><span class="sv">{n_skip}</span> Skipped</div>'}
        {"" if n_warn_subs == 0 else f'<div class="stat-chip warn"><span class="sv">{n_warn_subs}</span> Warnings</div>'}
        {"" if n_retry_subs == 0 else f'<div class="stat-chip retry"><span class="sv">{n_retry_subs}</span> Retries</div>'}
        <div class="stat-chip dur"><span class="sv">{_fmt_duration(duration)}</span> Duration</div>
    </div>
  </div>
</div>

<div class="content">
{body_html}
</div>

<div id="lightbox" class="lightbox" onclick="closeLB()">
    <button class="close-btn" onclick="closeLB()"><span class="mi">&#xe5cd;</span></button>
    <img id="lb-img" src="" alt="screenshot"/>
</div>

<div class="footer">
    eBay E2E Test Framework &middot; Playwright + pytest &middot; Generated {time.strftime("%Y-%m-%d %H:%M:%S")}
</div>

<script>{_JS}</script>
</body>
</html>""", encoding="utf-8")

    return str(filepath)


def generate_run_summary(
    records: List[ScenarioRecord],
    output_dir: Optional[str] = None,
    run_id: str = "",
) -> str:
    """Generate a summary HTML report for all scenarios in a test run."""
    out = Path(output_dir) if output_dir else REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    rid = run_id or timestamp
    filename = f"summary_{rid}.html"
    filepath = out / filename

    total_scenarios = len(records)
    total_pass = sum(1 for r in records if r.status.lower() == "pass")
    total_fail = sum(1 for r in records if r.status.lower() == "fail")
    total_skip = sum(1 for r in records if r.status.lower() == "skip")
    total_steps = sum(len(r.steps) for r in records)
    total_subs = sum(sum(len(s.sub_steps) for s in r.steps) for r in records)
    total_warn_subs = sum(
        sum(1 for sub in s.sub_steps if sub.status.lower() == "warn")
        for r in records for s in r.steps
    )
    total_retry_subs = sum(
        sum(1 for sub in s.sub_steps if sub.status.lower() == "retry")
        for r in records for s in r.steps
    )
    total_duration = sum((r.finished_at - r.started_at) for r in records if r.finished_at)
    pass_rate = round(total_pass / max(total_scenarios, 1) * 100)
    ring_cls = "pass" if total_fail == 0 else ("fail" if pass_rate < 50 else "warn")

    scenarios_html = "\n<hr style='border-color:var(--border);margin:32px auto;max-width:1200px;opacity:.3;'>\n".join(
        _build_scenario_html(r, f"s{i}") for i, r in enumerate(records)
    )

    filepath.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Test Run Summary \u2014 {html_mod.escape(rid)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="bg-mesh"></div>

<div class="header">
  <div class="header-inner">
    <div class="header-top">
        <div class="result-ring {ring_cls}">
            <div class="glow"></div>
            {pass_rate}%
        </div>
        <div>
            <h1>eBay E2E Test Run Summary</h1>
            <div class="sub">{time.strftime("%Y/%m/%d %H:%M:%S")} &middot; Run ID: {html_mod.escape(rid)} &middot; {total_scenarios} scenarios &middot; {total_steps} steps &middot; {total_subs} actions</div>
        </div>
        <div class="toolbar">
            <button onclick="expandAll()">Expand All</button>
            <button onclick="collapseAll()">Collapse All</button>
        </div>
    </div>
    <div class="stats-bar">
        <div class="stat-chip total"><span class="sv">{total_scenarios}</span> Scenarios</div>
        <div class="stat-chip pass"><span class="sv">{total_pass}</span> Passed</div>
        <div class="stat-chip fail"><span class="sv">{total_fail}</span> Failed</div>
        {"" if total_skip == 0 else f'<div class="stat-chip"><span class="sv">{total_skip}</span> Skipped</div>'}
        {"" if total_warn_subs == 0 else f'<div class="stat-chip warn"><span class="sv">{total_warn_subs}</span> Warnings</div>'}
        {"" if total_retry_subs == 0 else f'<div class="stat-chip retry"><span class="sv">{total_retry_subs}</span> Retries</div>'}
        <div class="stat-chip total"><span class="sv">{total_steps}</span> Steps</div>
        <div class="stat-chip dur"><span class="sv">{_fmt_duration(total_duration)}</span> Duration</div>
    </div>
  </div>
</div>

<div class="content">
{scenarios_html}
</div>

<div id="lightbox" class="lightbox" onclick="closeLB()">
    <button class="close-btn" onclick="closeLB()"><span class="mi">&#xe5cd;</span></button>
    <img id="lb-img" src="" alt="screenshot"/>
</div>

<div class="footer">
    eBay E2E Test Framework &middot; Playwright + pytest &middot; Generated {time.strftime("%Y-%m-%d %H:%M:%S")}
</div>

<script>{_JS}</script>
</body>
</html>""", encoding="utf-8")

    return str(filepath)
