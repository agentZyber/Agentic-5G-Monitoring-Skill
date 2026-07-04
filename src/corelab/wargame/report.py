"""Evidence pack — markdown run reports + a self-contained HTML dashboard for the audit.

Turns a run into the artefacts a consortium-entry audit wants to see: the scored outcome, the
turn-by-turn timeline, the human-control decision log, the defender leaderboard, and a provenance
footer (sovereign/local, reproducible). No external assets — the HTML opens anywhere, offline.
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

from corelab.wargame.engine import WarGameResult
from corelab.wargame.scenario import WarGameScenario


def result_markdown(result: WarGameResult) -> str:
    s = result.score
    lines = [
        f"# War-game: {result.scenario_id}",
        f"**{result.red}**  vs  **{result.blue}**  —  outcome: {'✅ mission held' if s.success else '❌ mission lost'}",
        "",
        f"- availability: **{s.availability:.0%}** · time-to-detect: **{s.time_to_detect}** turn(s) · "
        f"neutralised: **{s.threats_neutralised}/{s.threats_injected}** · unauthorized actions: **{s.unauthorized_applies}**",
        "",
        "| check | result | detail |", "|---|---|---|",
    ]
    for c in s.checks:
        lines.append(f"| {c.name} | {'✅' if c.passed else '❌'} | {c.detail} |")
    lines += ["", "## Timeline", "| turn | red | blue | mission |", "|---|---|---|---|"]
    for t in result.timeline:
        lines.append(f"| {t.turn} | {t.red_action or '—'} | {t.blue_action or '—'} | "
                     f"{'healthy' if t.mission_healthy else 'DEGRADED'} |")
    lines += ["", "## Human-control (doctrine) decisions"]
    if result.approval_log:
        for e in result.approval_log:
            lines.append(f"- {'APPROVED' if e['approved'] else 'DENIED'} · {e['action']}"
                         f"({e['args']}) — {e['approver'] or e['reason']}")
    else:
        lines.append("- (no consequential actions requested)")
    return "\n".join(lines)


def _rows(board: List[Dict[str, Any]]) -> str:
    out = []
    for i, r in enumerate(board, 1):
        ttd = "—" if r["mean_time_to_detect"] is None else r["mean_time_to_detect"]
        out.append(f"<tr><td>{i}</td><td>{html.escape(r['blue'])}</td>"
                   f"<td>{r['win_rate']:.0%}</td><td>{r['mean_availability']:.0%}</td><td>{ttd}</td></tr>")
    return "".join(out)


def _timeline_rows(result: WarGameResult) -> str:
    out = []
    for t in result.timeline:
        cls = "ok" if t.mission_healthy else "bad"
        out.append(f"<tr><td>{t.turn}</td><td>{html.escape(t.red_action or '—')}</td>"
                   f"<td>{html.escape(t.blue_action or '—')}</td>"
                   f"<td class='{cls}'>{'healthy' if t.mission_healthy else 'DEGRADED'}</td></tr>")
    return "".join(out)


def _approval_rows(result: WarGameResult) -> str:
    if not result.approval_log:
        return "<tr><td colspan=3>(no consequential actions requested)</td></tr>"
    out = []
    for e in result.approval_log:
        tag = "ok" if e["approved"] else "bad"
        out.append(f"<tr><td class='{tag}'>{'APPROVED' if e['approved'] else 'DENIED'}</td>"
                   f"<td>{html.escape(e['action'])}({html.escape(str(e['args']))})</td>"
                   f"<td>{html.escape(e['approver'] or e['reason'])}</td></tr>")
    return "".join(out)


def dashboard_html(scenario: WarGameScenario, results: List[WarGameResult],
                   board: List[Dict[str, Any]], featured: Optional[WarGameResult] = None,
                   model: str = "local (sovereign)") -> str:
    featured = featured or (results[-1] if results else None)
    s = featured.score if featured else None
    verdict = ("✅ mission held" if (s and s.success) else "❌ mission lost") if s else "—"
    tl = _timeline_rows(featured) if featured else ""
    ap = _approval_rows(featured) if featured else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>War-game evidence — {html.escape(scenario.scenario_id)}</title>
<style>
:root{{--bg:#0e1420;--card:#161f2e;--ink:#e6edf6;--mut:#8aa0bd;--ok:#37d67a;--bad:#ff5c6c;--line:#243349;--accent:#5aa9ff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:28px}} h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--mut);margin-bottom:18px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 10px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{color:var(--mut);font-weight:600}} .ok{{color:var(--ok)}} .bad{{color:var(--bad)}} .big{{font-size:15px}}
.badge{{display:inline-block;padding:2px 8px;border:1px solid var(--line);border-radius:99px;color:var(--mut);font-size:12px;margin-right:6px}}
.verdict{{font-size:16px;font-weight:700}}
</style></head><body><div class="wrap">
<h1>Red/Blue War-Game — Evidence Pack</h1>
<div class="sub">{html.escape(scenario.title)}</div>
<div style="margin-bottom:16px">
  <span class="badge">sovereign · {html.escape(model)}</span>
  <span class="badge">human-in-the-loop</span>
  <span class="badge">non-kinetic simulation</span>
  <span class="badge">reproducible</span>
</div>
<div class="grid">
  <div class="card"><h2>Defender leaderboard (vs {len({r.red for r in results})} adversary profiles)</h2>
    <table><tr><th>#</th><th>defender</th><th>win rate</th><th>availability</th><th>t-to-detect</th></tr>{_rows(board)}</table></div>
  <div class="card"><h2>Featured run · {html.escape(featured.red) if featured else '—'} vs {html.escape(featured.blue) if featured else '—'}</h2>
    <div class="verdict">{verdict}</div>
    <div class="big" style="color:var(--mut);margin-top:6px">availability {s.availability:.0%} · detect {s.time_to_detect} turn(s) · neutralised {s.threats_neutralised}/{s.threats_injected} · unauthorized {s.unauthorized_applies}</div>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Turn-by-turn timeline</h2>
  <table><tr><th>turn</th><th>red move</th><th>blue move</th><th>mission</th></tr>{tl}</table></div>
<div class="card" style="margin-top:16px"><h2>Human-control (doctrine) decision log</h2>
  <table><tr><th>decision</th><th>action</th><th>authority</th></tr>{ap}</table>
  <div style="color:var(--mut);margin-top:8px;font-size:12px">Every consequential action is gated on human approval and logged — the AI proposes, a human disposes.</div></div>
<div class="sub" style="margin-top:16px;font-size:12px">Provenance: judged programmatically (state-based), seeded &amp; reproducible, runs fully on local models (air-gappable). {html.escape(scenario.description)}</div>
</div></body></html>"""
