"""Showcase dashboard — a slick, operations-console (Palantir-style) view of a war-game run set.

Single self-contained HTML (no external assets): dark tactical theme, a battlespace node-graph, a
turn scrubber, per-run stat tiles, the defender leaderboard, and the human-control decision log.
Consumes the JSON that :meth:`WarGameResult.to_dict` produces, so it works offline and embeds
everything needed to explore every matchup interactively.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def _leaderboard(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    agg: Dict[str, Dict[str, Any]] = {}
    for r in results:
        row = agg.setdefault(r["blue"], {"blue": r["blue"], "n": 0, "wins": 0, "av": 0.0})
        row["n"] += 1
        row["wins"] += 1 if r["score"]["success"] else 0
        row["av"] += r["score"]["availability"]
    board = [{"blue": v["blue"], "win_rate": v["wins"] / v["n"], "mean_availability": v["av"] / v["n"]}
             for v in agg.values()]
    board.sort(key=lambda x: (x["win_rate"], x["mean_availability"]), reverse=True)
    return board


def _default_index(results: List[Dict[str, Any]]) -> int:
    for i, r in enumerate(results):
        if r["score"]["success"] and r["score"]["threats_injected"] >= 3:
            return i
    for i, r in enumerate(results):
        if r["score"]["success"]:
            return i
    return 0


def showcase_html(scenarios: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    payload = json.dumps({
        "scenarios": scenarios, "results": results,
        "board": _leaderboard(results), "default": _default_index(results),
    }, default=str)
    return _TEMPLATE.replace("__PAYLOAD__", payload)


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CORE Lab · NCSRD — Adversarial War-Game Console</title>
<style>
:root{
 --bg:#070b12;--panel:#0d131e;--panel2:#111a28;--line:#182335;--line2:#25344a;
 --ink:#dbe6f2;--mut:#6d829e;--dim:#3f5169;
 --cy:#3ad0d8;--am:#ffb020;--rd:#ff4d5e;--gn:#35d69f;--bl:#4aa8ff;
 --mono:ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:13px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
 background:radial-gradient(1100px 560px at 72% -12%,#101d2e 0%,transparent 58%),var(--bg);
 background-attachment:fixed}
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.05;
 background-image:linear-gradient(var(--line2) 1px,transparent 1px),linear-gradient(90deg,var(--line2) 1px,transparent 1px);
 background-size:46px 46px}
.app{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:16px 20px 44px}
.bar{display:flex;align-items:center;gap:14px;border:1px solid var(--line);border-radius:11px;padding:12px 16px;margin-bottom:14px;
 background:linear-gradient(180deg,#0c151f,#0a101a)}
.brand{font-family:var(--mono);font-weight:700;letter-spacing:.16em;font-size:13px}
.brand b{color:var(--cy)}.brand span{color:var(--mut);font-weight:400}
.pills{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}
.pill{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--mut);border:1px solid var(--line2);
 border-radius:99px;padding:3px 10px;text-transform:uppercase}
.pill.live{color:var(--gn);border-color:#1c3b30}
.pill.live::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--gn);
 margin-right:6px;box-shadow:0 0 9px var(--gn);animation:pulse 1.7s infinite}
@keyframes pulse{50%{opacity:.3}}
.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}
.panel{border:1px solid var(--line);border-radius:11px;padding:14px;background:linear-gradient(180deg,var(--panel),#0b111b)}
.h{font-family:var(--mono);font-size:10px;letter-spacing:.17em;color:var(--mut);text-transform:uppercase;margin:0 0 11px;
 display:flex;align-items:center;gap:8px}
.h::before{content:"";width:6px;height:6px;background:var(--cy);border-radius:1px;box-shadow:0 0 9px var(--cy)}
.h .r{margin-left:auto;color:var(--dim);letter-spacing:.08em}
.ctl{display:flex;align-items:center;gap:12px;margin-bottom:13px;flex-wrap:wrap}
select{font-family:var(--mono);background:#0a1220;color:var(--ink);border:1px solid var(--line2);border-radius:8px;
 padding:7px 11px;font-size:12px;outline:none}
select:focus{border-color:var(--cy)}
#play{font-family:var(--mono);background:#0a1220;color:var(--cy);border:1px solid var(--line2);border-radius:8px;padding:7px 15px;font-size:12px;cursor:pointer;letter-spacing:.06em}
#play:hover{border-color:var(--cy);box-shadow:0 0 10px rgba(58,208,216,.25)}
.scrub{display:flex;align-items:center;gap:9px;flex:1;min-width:210px;font-family:var(--mono);font-size:11px;color:var(--mut)}
.scrub input{flex:1;accent-color:var(--cy)}
.verdict{font-family:var(--mono);font-weight:700;letter-spacing:.04em;font-size:15px}
.held{color:var(--gn)}.lost{color:var(--rd)}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:12px 0 4px}
.tile{border:1px solid var(--line);background:var(--panel2);border-radius:9px;padding:11px 12px}
.tile .k{font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;color:var(--mut);text-transform:uppercase}
.tile .v{font-family:var(--mono);font-size:25px;font-weight:700;margin-top:5px;line-height:1}
.cy{color:var(--cy)}.gn{color:var(--gn)}.am{color:var(--am)}.rd{color:var(--rd)}.bl{color:var(--bl)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;color:var(--mut);text-transform:uppercase;font-weight:600}
.mono{font-family:var(--mono)}
tr.cur td{background:rgba(58,208,216,.06)}
tr.deg td:last-child{color:#ffb9c0}
.lb .row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.lb .nm{font-family:var(--mono);font-size:11.5px;width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lb .track{flex:1;height:7px;background:#0a1220;border:1px solid var(--line);border-radius:99px;overflow:hidden}
.lb .fill{height:100%;background:linear-gradient(90deg,#1b6a6f,var(--cy));box-shadow:0 0 10px rgba(58,208,216,.35)}
.lb .pct{font-family:var(--mono);width:42px;text-align:right;color:var(--cy);font-size:12px}
.legend{display:flex;gap:15px;font-family:var(--mono);font-size:10px;color:var(--mut);margin-top:9px;flex-wrap:wrap}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.tag{font-family:var(--mono);font-size:10px;padding:2px 7px;border-radius:5px;border:1px solid var(--line2)}
.tag.ap{color:var(--gn);border-color:#1c3b30}.tag.dn{color:var(--rd);border-color:#3b1c22}
.foot{color:var(--dim);font-size:11px;margin-top:16px;font-family:var(--mono);letter-spacing:.03em}
.note{color:var(--mut);font-size:11px;margin-top:9px}
</style></head>
<body><div class="app">
 <div class="bar">
  <div class="brand"><b>CORE LAB</b> <span>·</span> <b style="color:var(--am)">NCSRD</b> · ADVERSARIAL WAR-GAME <span id="scn"></span></div>
  <div class="pills">
   <span class="pill live">Operational</span>
   <span class="pill">Sovereign</span><span class="pill">Human-in-the-loop</span>
   <span class="pill">Non-kinetic</span><span class="pill">Reproducible</span>
  </div>
 </div>

 <div class="ctl">
  <select id="run"></select>
  <div class="scrub"><span>TURN</span><input id="turn" type="range" min="1" value="1"><span id="turnlbl" class="mono cy"></span></div>
  <button id="play">▶ PLAY</button>
 </div>

 <div class="grid">
  <div class="panel">
   <div class="h">Battlespace <span class="r" id="bsstat"></span></div>
   <svg id="bs" viewBox="0 0 520 300" style="width:100%;height:auto;display:block"></svg>
   <div class="legend">
    <span><span class="dot" style="background:var(--cy)"></span>mission asset</span>
    <span><span class="dot" style="background:var(--rd)"></span>active threat</span>
    <span><span class="dot" style="background:var(--gn)"></span>neutralised</span>
    <span><span class="dot" style="background:var(--dim)"></span>pending</span>
    <span><span class="dot" style="background:var(--bl)"></span>defender</span>
   </div>
  </div>
  <div class="panel">
   <div class="h">Mission outcome</div>
   <div id="verdict" class="verdict"></div>
   <div class="tiles">
    <div class="tile"><div class="k">Availability</div><div class="v cy" id="t_av"></div></div>
    <div class="tile"><div class="k">Time-to-detect</div><div class="v bl" id="t_ttd"></div></div>
    <div class="tile"><div class="k">Neutralised</div><div class="v gn" id="t_neut"></div></div>
    <div class="tile"><div class="k">Unauthorized</div><div class="v" id="t_un"></div></div>
   </div>
   <div class="h" style="margin-top:14px">Defender leaderboard <span class="r" id="lbn"></span></div>
   <div class="lb" id="lb"></div>
  </div>
 </div>

 <div class="grid" style="margin-top:14px">
  <div class="panel">
   <div class="h">Engagement timeline</div>
   <table><thead><tr><th>T</th><th>Red move</th><th>Blue move</th><th>Mission</th></tr></thead>
   <tbody id="tl"></tbody></table>
  </div>
  <div class="panel">
   <div class="h">Human-control · doctrine decisions</div>
   <table><thead><tr><th>Decision</th><th>Action</th><th>Authority</th></tr></thead>
   <tbody id="ap"></tbody></table>
   <div class="note">Every consequential action is gated on human approval and logged — the AI proposes, a human disposes.</div>
  </div>
 </div>

 <div class="foot" id="foot"></div>
</div>
<script>
const D=__PAYLOAD__, R=D.results;
const $=s=>document.querySelector(s), esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
$('#foot').textContent='Provenance: state-based programmatic judge · seeded & reproducible · sovereign local models (air-gappable) · '+Object.keys(D.scenarios).length+' scenarios · '+R.length+' matchups';
// leaderboard (static)
$('#lbn').textContent=D.board.length+' defenders';
$('#lb').innerHTML=D.board.map(b=>{const w=Math.round(b.win_rate*100);
 return `<div class="row"><div class="nm">${esc(b.blue)}</div><div class="track"><div class="fill" style="width:${w}%"></div></div><div class="pct">${w}%</div></div>`;}).join('');
// run selector
$('#run').innerHTML=R.map((r,i)=>`<option value="${i}">${esc(r.scenario_id)} · ${esc(r.red)} ✦ ${esc(r.blue)} — ${r.score.success?'HELD':'lost'}</option>`).join('');
$('#run').value=D.default;

function threatsOf(run){ // ordered unique threat ids + injection turn
 const seen={},order=[];
 run.timeline.forEach(t=>(t.injected||[]).forEach(id=>{if(!(id in seen)){seen[id]=t.turn;order.push(id);}}));
 return {order,inj:seen};
}
function drawRadio(run,turn){
 const r=run.timeline[turn-1]?run.timeline[turn-1].radio:null; if(!r) return;
 const cx=200,cy=150,R0=120,n=r.ues.length,cqiCol=c=>c>=13?'#35d69f':c>=8?'#ffb020':'#ff4d5e',powered=r.cell_power_db>=0;
 let s=`<defs><filter id="g"><feGaussianBlur stdDeviation="3.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
 const pos=r.ues.map((u,k)=>{const a=(-Math.PI/2)+(k-(n-1)/2)*0.75;return{x:cx+Math.cos(a)*R0,y:cy+Math.sin(a)*R0,u};});
 pos.forEach(p=>{const col=cqiCol(p.u.cqi),deg=p.u.cqi<12;s+=`<line x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="${col}" stroke-width="${deg?1.9:1.2}" opacity="${deg?.9:.5}"/>`;});
 s+=`<circle cx="${cx}" cy="${cy}" r="30" fill="#0a1626" stroke="${powered?'#3ad0d8':'#ff4d5e'}" stroke-width="2" filter="url(#g)"/>`;
 s+=`<text x="${cx}" y="${cy-4}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="10" fill="${powered?'#8fe9ec':'#ff8f99'}">CELL-1</text>`;
 s+=`<text x="${cx}" y="${cy+10}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9" fill="${powered?'#5f7690':'#ff8f99'}">${powered?'nominal':r.cell_power_db+' dB'}</text>`;
 pos.forEach(p=>{const col=cqiCol(p.u.cqi),deg=p.u.cqi<12;
  s+=`<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="17" fill="#0e1524" stroke="${col}" stroke-width="1.9" ${deg?'filter=\"url(#g)\"':''}/>`;
  s+=`<text x="${p.x.toFixed(1)}" y="${(p.y-2).toFixed(1)}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8" fill="${col}">UE${p.u.id}</text>`;
  s+=`<text x="${p.x.toFixed(1)}" y="${(p.y+9).toFixed(1)}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8.5" fill="${col}">CQI ${p.u.cqi}</text>`;});
 $('#bs').innerHTML=s;
 $('#bsstat').textContent=`cell power ${powered?'0':r.cell_power_db} dB · min CQI ${Math.min(...r.ues.map(u=>u.cqi))}`;
}
function drawBS(run,turn){
 if(run.timeline[turn-1]&&run.timeline[turn-1].radio){ drawRadio(run,turn); return; }
 const {order,inj}=threatsOf(run), active=new Set(run.timeline[turn-1]?run.timeline[turn-1].active_threats.filter(Boolean):[]);
 const W=520,H=300,cx=200,cy=150, defx=430,defy=150;
 let s=`<defs><filter id="g"><feGaussianBlur stdDeviation="3.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
 // links
 order.forEach((id,k)=>{const a=(-Math.PI/2)+ (k-(order.length-1)/2)*0.62, R0=118, x=cx+Math.cos(a)*R0, y=cy+Math.sin(a)*R0;
  const injd=inj[id]<=turn, act=active.has(id), col=!injd?'#26334a':act?'#ff4d5e':'#35d69f';
  s+=`<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${col}" stroke-width="${act?1.6:1}" stroke-dasharray="${injd?'':'3 4'}" opacity="${injd?.8:.4}"/>`;});
 // defender + link
 s+=`<line x1="${cx}" y1="${cy}" x2="${defx}" y2="${defy}" stroke="#274b6e" stroke-width="1.4"/>`;
 // mission node
 const deg=[...active].length>0;
 s+=`<circle cx="${cx}" cy="${cy}" r="30" fill="#0a1626" stroke="${deg?'#ff4d5e':'#3ad0d8'}" stroke-width="2" filter="url(#g)"/>`;
 s+=`<text x="${cx}" y="${cy-2}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="10" fill="${deg?'#ff8f99':'#8fe9ec'}">MISSION</text>`;
 s+=`<text x="${cx}" y="${cy+11}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8.5" fill="#5f7690">${esc((D.scenarios[run.scenario_id]||{}).mission_asset)}</text>`;
 // threat nodes
 order.forEach((id,k)=>{const a=(-Math.PI/2)+(k-(order.length-1)/2)*0.62, R0=118, x=cx+Math.cos(a)*R0, y=cy+Math.sin(a)*R0;
  const injd=inj[id]<=turn, act=active.has(id), col=!injd?'#3f5169':act?'#ff4d5e':'#35d69f';
  s+=`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="11" fill="#0e1524" stroke="${col}" stroke-width="1.8" ${act?'filter="url(#g)"':''}/>`;
  s+=`<text x="${x.toFixed(1)}" y="${(y+3).toFixed(1)}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8.5" fill="${col}">${esc(id)}</text>`;});
 // defender node
 s+=`<circle cx="${defx}" cy="${defy}" r="20" fill="#0a1626" stroke="#4aa8ff" stroke-width="2"/>`;
 s+=`<text x="${defx}" y="${defy+3}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8.5" fill="#9ecbff">BLUE</text>`;
 $('#bs').innerHTML=s;
 $('#bsstat').textContent=`${active.size} active / ${order.length} threats`;
}
function render(){
 const run=R[+$('#run').value], s=run.score, N=run.timeline.length;
 $('#scn').textContent=' · '+((D.scenarios[run.scenario_id]||{}).title||run.scenario_id);
 const turnEl=$('#turn'); turnEl.max=N; let turn=Math.min(+turnEl.value,N); turnEl.value=turn;
 $('#turnlbl').textContent=turn+' / '+N;
 $('#verdict').innerHTML=(s.success?'<span class="held">&#10004; MISSION HELD</span>':'<span class="lost">&#10008; MISSION LOST</span>')+` <span class="mut" style="font-size:12px">· ${esc(run.red)} vs ${esc(run.blue)}</span>`;
 $('#t_av').textContent=Math.round(s.availability*100)+'%';
 $('#t_ttd').textContent=(s.time_to_detect==null?'—':s.time_to_detect);
 $('#t_neut').textContent=s.threats_neutralised+'/'+s.threats_injected;
 const un=$('#t_un'); un.textContent=s.unauthorized_applies; un.className='v '+(s.unauthorized_applies?'rd':'gn');
 // timeline
 $('#tl').innerHTML=run.timeline.map(t=>`<tr class="${t.turn===turn?'cur ':''}${t.mission_healthy?'':'deg'}"><td class="mono">${t.turn}</td><td class="mono">${esc(t.red||'—')}</td><td class="mono">${esc(t.blue||'—')}</td><td class="mono ${t.mission_healthy?'gn':'rd'}">${t.mission_healthy?'healthy':'DEGRADED'}</td></tr>`).join('');
 // doctrine log
 const ap=run.approval_log||[];
 $('#ap').innerHTML=ap.length?ap.map(e=>`<tr><td><span class="tag ${e.approved?'ap':'dn'}">${e.approved?'APPROVED':'DENIED'}</span></td><td class="mono">${esc(e.action)}(${esc(JSON.stringify(e.args))})</td><td class="mono mut">${esc(e.approver||e.reason)}</td></tr>`).join(''):'<tr><td colspan=3 class="mut">no consequential actions requested</td></tr>';
 drawBS(run,turn);
}
let timer=null;
function stopPlay(){ if(timer){clearInterval(timer);timer=null;$('#play').textContent='▶ PLAY';} }
$('#play').addEventListener('click',()=>{
 if(timer){stopPlay();return;}
 const t=$('#turn'); if(+t.value>=+t.max){t.value=1;}      // replay from the top
 $('#play').textContent='⏸ PAUSE';
 timer=setInterval(()=>{const t=$('#turn'); if(+t.value>=+t.max){stopPlay();return;} t.value=+t.value+1; render();},850);
 render();
});
$('#run').addEventListener('change',()=>{stopPlay();$('#turn').value=R[+$('#run').value].timeline.length;render();});
$('#turn').addEventListener('input',()=>{stopPlay();render();});
$('#run').value=D.default; $('#turn').value=R[D.default].timeline.length; render();
</script></body></html>"""
