"""
Genesis Companion — Floating Assistant UI (self-contained web app).

Generates a single self-contained HTML application that IS the Floating Assistant:
a small draggable status **bubble** that expands into a chat-first **panel** and
hands off to the **Canvas**. Zero setup — it opens in any browser (and drops into
a Tauri shell later unchanged).

It speaks the real CompanionServer protocol (streaming/server.py):
  - connects to ws://127.0.0.1:<port>
  - auth handshake: {"type":"auth","token":"..."}
  - then receives engine/gate/session/committee events and renders them live
  - sends user intents / approvals back

Design system is the live site's (extracted from production CSS):
  Geist / Geist Mono / Fraunces · paper #f4f2ec · ink #16140f · accent #0b62f5.
Dark mode mirrors docs/pro.html tokens.

Honesty: with no server connected, the bubble shows an honest "offline / idle"
state and never fabricates progress. The UI is presentation-only — all work runs
in the engines behind the WebSocket.
"""

from __future__ import annotations

import json
from pathlib import Path

# The default CompanionServer port (streaming/server.py: _PORT = 47291).
DEFAULT_PORT = 47291


def render_companion_html(*, ws_port: int = DEFAULT_PORT, ws_token: str = "",
                          theme: str = "light") -> str:
    """Return the complete self-contained Floating Assistant HTML.

    ws_port / ws_token wire the UI to a running CompanionServer. If the server is
    not up, the UI stays in an honest offline/idle state (no fake activity).
    """
    cfg = json.dumps({"port": ws_port, "token": ws_token, "theme": theme})
    return _HTML.replace("/*__CONFIG__*/", f"window.GENESIS_CFG = {cfg};")


def write_companion_html(project_root: Path | str = ".", *,
                         ws_port: int = DEFAULT_PORT, ws_token: str = "",
                         theme: str = "light",
                         out_name: str = "companion.html") -> Path | None:
    """Write the Floating Assistant HTML to .genesis/ui/<out_name>. Returns the
    path (open it in a browser), or None on I/O error."""
    target = Path(project_root) / ".genesis" / "ui" / out_name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_companion_html(ws_port=ws_port, ws_token=ws_token,
                                                 theme=theme), encoding="utf-8")
        return target
    except OSError:
        return None


# ---------------------------------------------------------------------------
# The self-contained app (HTML + CSS + JS). No external assets except fonts.
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Genesis Assistant</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..600;1,9..144,400..600&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#f4f2ec; --ink:#16140f; --ink2:#4a463d; --muted:#7c776b;
  --line:#dcd8cd; --line2:#cac4b5; --accent:#0b62f5; --card:#fbfaf7; --white:#fff;
  --green:#1a7f4b; --amber:#b26a00; --red:#c0392b;
  --sans:'Geist',-apple-system,sans-serif; --mono:'Geist Mono',monospace; --serif:'Fraunces',Georgia,serif;
}
[data-theme="dark"]{
  --paper:#0d1017; --ink:#e4ecf8; --ink2:#c2d0e6; --muted:#5e7291;
  --line:#2b3650; --line2:#232d42; --accent:#5b8ef0; --card:#141922; --white:#0f141d;
  --green:#3ecf8e; --amber:#f59e0b; --red:#f87171;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:var(--sans);background:transparent;color:var(--ink);-webkit-font-smoothing:antialiased;overflow:hidden}

/* ── BUBBLE (collapsed) ─────────────────────────────────────────── */
.bubble{position:fixed;right:24px;bottom:24px;z-index:1000;display:flex;align-items:center;gap:12px;
  background:var(--white);border:1px solid var(--line);border-radius:16px;padding:10px 16px 10px 10px;
  cursor:pointer;user-select:none;box-shadow:0 2px 4px #16140f10,0 20px 44px -12px #16140f2e,0 0 0 1px #0b62f508;
  transition:transform .18s ease,box-shadow .18s;max-width:340px}
.bubble:hover{transform:translateY(-2px);box-shadow:0 4px 8px #16140f14,0 28px 56px -12px #16140f38}
.bubble.hidden{display:none}
.mark{width:38px;height:38px;border-radius:11px;flex-shrink:0;display:grid;place-items:center;position:relative;
  background:linear-gradient(135deg,var(--accent),#3b3bd6);color:#fff;font-family:var(--mono);font-weight:700;font-size:16px}
.ring{position:absolute;inset:-3px;border-radius:13px;border:2px solid transparent}
.ring.active{border-color:var(--accent);animation:spin 1.4s linear infinite;border-right-color:transparent;border-top-color:transparent}
.ring.warn{border-color:var(--amber)}
.ring.crit{border-color:var(--red)}
.ring.ok{border-color:var(--green)}
@keyframes spin{to{transform:rotate(360deg)}}
.b-body{min-width:0}
.b-title{font-size:13px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px}
.b-sub{font-size:11px;color:var(--muted);font-family:var(--mono);white-space:nowrap}
.b-bar{height:3px;background:var(--line);border-radius:3px;margin-top:6px;overflow:hidden;width:220px}
.b-bar span{display:block;height:100%;background:var(--accent);width:0;transition:width .3s}

/* ── PANEL (expanded) ───────────────────────────────────────────── */
.panel{position:fixed;right:24px;bottom:24px;z-index:1001;width:380px;height:min(600px,88vh);
  background:var(--white);border:1px solid var(--line);border-radius:18px;display:none;flex-direction:column;overflow:hidden;
  box-shadow:0 8px 16px #16140f14,0 40px 80px -16px #16140f45,0 0 0 1px #0b62f50a}
.panel.open{display:flex;animation:rise .2s ease}
@keyframes rise{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
.p-head{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line);background:var(--card)}
.p-head .mark{width:30px;height:30px;border-radius:9px;font-size:13px}
.p-name{font-weight:600;font-size:15px;flex:1}
.p-name small{display:block;font-family:var(--mono);font-size:10.5px;color:var(--muted);font-weight:400}
.icn{width:30px;height:30px;border-radius:8px;border:1px solid transparent;background:transparent;color:var(--muted);
  cursor:pointer;display:grid;place-items:center;font-size:16px;transition:all .15s}
.icn:hover{background:var(--card);color:var(--ink);border-color:var(--line)}

.tabs{display:flex;gap:2px;padding:8px 12px 0;border-bottom:1px solid var(--line)}
.tab{font-size:12.5px;font-weight:500;color:var(--muted);padding:8px 12px;cursor:pointer;border-bottom:2px solid transparent;font-family:var(--sans)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent)}

.p-body{flex:1;overflow-y:auto;padding:16px}
.view{display:none}.view.on{display:block}

/* chat */
.msg{margin-bottom:14px;max-width:88%;font-size:14px;line-height:1.5}
.msg.user{margin-left:auto;background:var(--accent);color:#fff;padding:10px 14px;border-radius:14px 14px 4px 14px}
.msg.bot{color:var(--ink)}
.msg.bot .who{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.08em}

/* progress list (multi-engine) */
.prog{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:8px 0}
.prow{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--line);font-size:13px}
.prow:last-child{border-bottom:none}
.pdot{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:var(--line2)}
.pdot.run{background:var(--accent);box-shadow:0 0 0 3px #0b62f522}
.pdot.done{background:var(--green)}
.pdot.fail{background:var(--red)}
.pdot.wait{background:var(--line2)}
.pname{flex:1;min-width:0}
.pname b{font-weight:600;display:block}
.pname small{color:var(--muted);font-size:11px}
.ppct{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--accent)}
.pq{font-family:var(--mono);font-size:11px;color:var(--muted)}

/* quick actions */
.qa{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px}
.qbtn{display:flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--card);border-radius:10px;
  padding:11px 12px;font-size:13px;font-weight:500;color:var(--ink);cursor:pointer;font-family:var(--sans);transition:all .15s;text-align:left}
.qbtn:hover{border-color:var(--accent);color:var(--accent)}
.qbtn .qi{font-size:15px}

/* approval card */
.approve{border:1px solid var(--amber);background:#b26a000d;border-radius:12px;padding:14px;margin:10px 0}
.approve h4{font-size:13px;color:var(--amber);margin-bottom:8px}
.approve .row{display:flex;gap:8px;margin-top:10px}

/* status strip */
.strip{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px;border-top:1px solid var(--line);background:var(--card)}
.chip{font-family:var(--mono);font-size:10.5px;padding:4px 9px;border-radius:999px;border:1px solid var(--line2);color:var(--ink2);background:var(--white)}
.chip b{color:var(--accent);font-weight:600}

/* composer */
.composer{display:flex;align-items:center;gap:8px;padding:12px 14px;border-top:1px solid var(--line)}
.composer input{flex:1;border:1px solid var(--line2);background:var(--card);border-radius:999px;padding:11px 16px;
  font-family:var(--sans);font-size:14px;color:var(--ink);outline:none}
.composer input:focus{border-color:var(--accent)}
.send{width:40px;height:40px;border-radius:999px;border:none;background:var(--accent);color:#fff;cursor:pointer;
  display:grid;place-items:center;font-size:16px;flex-shrink:0}
.send:hover{filter:brightness(1.08)}

/* activity slider (settings view) */
.setblk{margin-bottom:22px}
.setblk h4{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.levels{display:flex;gap:6px}
.lvl{flex:1;text-align:center;border:1px solid var(--line);border-radius:10px;padding:10px 4px;cursor:pointer;font-size:12px;transition:all .15s}
.lvl.on{border-color:var(--accent);background:#0b62f50a;color:var(--accent);font-weight:600}
.lvl small{display:block;font-size:10px;color:var(--muted);margin-top:2px}
.hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.6}
.hint code{font-family:var(--mono);font-size:11px;background:var(--card);border:1px solid var(--line);border-radius:5px;padding:1px 6px}

.empty{color:var(--muted);font-size:13px;text-align:center;padding:30px 10px;line-height:1.7}
.empty code{font-family:var(--mono);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:2px 8px;color:var(--accent)}
.foot{font-family:var(--mono);font-size:10px;color:var(--muted);text-align:center;padding:8px}
.conn{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:999px}
.conn.on{color:var(--green)} .conn.off{color:var(--muted)}
</style>
</head>
<body>

<!-- BUBBLE -->
<div class="bubble" id="bubble" onclick="Companion.expand()">
  <div class="mark">G<div class="ring" id="ring"></div></div>
  <div class="b-body">
    <div class="b-title" id="bTitle">Genesis — idle</div>
    <div class="b-sub" id="bSub">say hi or ask me to recover this project</div>
    <div class="b-bar" id="bBarWrap" style="display:none"><span id="bBar"></span></div>
  </div>
</div>

<!-- PANEL -->
<div class="panel" id="panel">
  <div class="p-head">
    <div class="mark">G</div>
    <div class="p-name">Genesis Assistant<small><span class="conn off" id="conn">● offline</span></small></div>
    <button class="icn" title="Open Canvas" onclick="Companion.canvas()">⛶</button>
    <button class="icn" title="Collapse" onclick="Companion.collapse()">×</button>
  </div>

  <div class="tabs">
    <div class="tab on" data-view="chat" onclick="Companion.tab('chat')">Chat</div>
    <div class="tab" data-view="status" onclick="Companion.tab('status')">Status</div>
    <div class="tab" data-view="actions" onclick="Companion.tab('actions')">Actions</div>
    <div class="tab" data-view="settings" onclick="Companion.tab('settings')">Settings</div>
  </div>

  <div class="p-body">
    <div class="view on" id="v-chat">
      <div class="msg bot"><div class="who">Genesis</div>Hi — I'm your engineering partner. Ask me to <b>recover this project</b>, <b>run research</b>, or <b>explain</b> anything. I'll show live engine progress here.</div>
      <div id="chatFeed"></div>
    </div>

    <div class="view" id="v-status">
      <div id="statusBody"><div class="empty">No active session yet.<br>Start one from <b>Chat</b> or <b>Actions</b>, and live engine progress appears here.</div></div>
    </div>

    <div class="view" id="v-actions">
      <div class="qa" id="qaGrid"></div>
    </div>

    <div class="view" id="v-settings">
      <div class="setblk">
        <h4>How active should Genesis be?</h4>
        <div class="levels" id="levels">
          <div class="lvl" data-lvl="quiet" onclick="Companion.setLevel('quiet')">Quiet<small>only when asked</small></div>
          <div class="lvl on" data-lvl="balanced" onclick="Companion.setLevel('balanced')">Balanced<small>important only</small></div>
          <div class="lvl" data-lvl="active" onclick="Companion.setLevel('active')">Active<small>proactive</small></div>
          <div class="lvl" data-lvl="expert" onclick="Companion.setLevel('expert')">Expert<small>co-pilot</small></div>
        </div>
        <div class="hint">Change anytime in chat: <code>help me less</code> · <code>be more proactive</code> · <code>stay quiet unless I ask</code></div>
      </div>
      <div class="setblk">
        <h4>Theme</h4>
        <div class="levels">
          <div class="lvl on" onclick="Companion.theme('light')">Light</div>
          <div class="lvl" onclick="Companion.theme('dark')">Dark</div>
        </div>
      </div>
      <div class="setblk">
        <h4>Privacy</h4>
        <div class="hint">Nothing leaves your machine. Genesis observes only what you allow, and never sends code, files, secrets, or prompts. <b>Enforced in code.</b></div>
      </div>
    </div>
  </div>

  <div class="strip" id="strip">
    <span class="chip">stage <b id="cStage">idle</b></span>
    <span class="chip">conf <b id="cConf">—</b></span>
    <span class="chip">risk <b id="cRisk">—</b></span>
  </div>

  <div class="composer">
    <input id="input" placeholder="Ask anything…" onkeydown="if(event.key==='Enter')Companion.send()"/>
    <button class="send" onclick="Companion.send()">➤</button>
  </div>
  <div class="foot">The Floating Assistant is the everyday interface. The Canvas is for deep work.</div>
</div>

<script>
/*__CONFIG__*/
const Companion = (() => {
  const cfg = window.GENESIS_CFG || {port:47291, token:'', theme:'light'};
  let ws=null, engines={}, session={stage:'idle',conf:null,risk:null}, level='balanced';

  // Contextual quick actions (computed; not a static dump)
  const ACTIONS = [
    {id:'recover', icon:'🔧', label:'Recover project', intent:'recover this project'},
    {id:'research', icon:'🔎', label:'Run research', intent:'run research on this'},
    {id:'explain', icon:'💡', label:'Explain', intent:'what is wrong here?'},
    {id:'review', icon:'🔍', label:'Review', intent:'review the architecture'},
    {id:'tests', icon:'✓', label:'Run tests', intent:'run the tests'},
    {id:'report', icon:'📄', label:'Open report', intent:'show me the report'},
    {id:'committee', icon:'⚖️', label:'Ask committee', intent:'ask the committee'},
    {id:'continue', icon:'↻', label:'Continue last', intent:'continue from last time'},
  ];

  function el(id){return document.getElementById(id)}
  function connect(){
    try{
      ws = new WebSocket('ws://127.0.0.1:'+cfg.port);
      ws.onopen = () => { ws.send(JSON.stringify({type:'auth',token:cfg.token})); setConn(true); };
      ws.onclose = () => { setConn(false); setTimeout(connect, 3000); };
      ws.onerror = () => {};
      ws.onmessage = (e) => { try{ handle(JSON.parse(e.data)); }catch(_){} };
    }catch(_){ setConn(false); }
  }
  function setConn(on){
    const c=el('conn'); c.className='conn '+(on?'on':'off'); c.textContent=on?'● live':'● offline';
  }
  function ring(cls){ el('ring').className='ring'+(cls?' '+cls:''); }

  // ── inbound event handling (matches streaming/events.py MessageType) ──
  function handle(m){
    const t=m.type||m.event, d=m.data||m.fields||m||{};
    if(t==='engine.start'){ engines[d.engine]={name:d.engine,label:d.label||d.engine,pct:0,state:'run'}; renderStatus(); ring('active'); setStage('executing'); }
    else if(t==='engine.progress'){ if(engines[d.engine]){engines[d.engine].pct=d.pct??d.progress??0; if(d.label)engines[d.engine].label=d.label;} renderStatus(); updateBubble(); }
    else if(t==='engine.done'){ if(engines[d.engine]){engines[d.engine].state='done';engines[d.engine].pct=100;} renderStatus(); updateBubble(); }
    else if(t==='engine.failed'){ if(engines[d.engine]){engines[d.engine].state='fail';} renderStatus(); ring('warn'); }
    else if(t==='gate.approval_required'||t==='gate.fired'){ showApproval(d); ring('warn'); }
    else if(t==='session.confidence'){ session.conf=d.confidence??d.conf; el('cConf').textContent=fmtConf(session.conf); }
    else if(t==='session.done'){ setStage('finished'); ring('ok'); botMsg('Done. '+(d.summary||'')); }
    else if(t==='committee.synthesis'){ botMsg('Committee: '+(d.recommendation||d.summary||'synthesis ready')); }
    else if(t==='voice.transcript'){ el('input').value=d.text||''; }
    else if(t==='diff.ready'){ botMsg('A change is ready for your review — open the Canvas to approve.'); }
  }
  function fmtConf(c){ return c==null?'—':(c<=1?Math.round(c*100)+'%':c); }

  function renderStatus(){
    const list=Object.values(engines);
    const body=el('statusBody');
    if(!list.length){ body.innerHTML='<div class="empty">No active session yet.<br>Start one from <b>Chat</b> or <b>Actions</b>.</div>'; return; }
    let h='<div class="prog">';
    for(const e of list){
      const cls={run:'run',done:'done',fail:'fail',wait:'wait'}[e.state]||'wait';
      const right = e.state==='wait'?'<span class="pq">Queued</span>'
                  : e.state==='fail'?'<span class="ppct" style="color:var(--red)">failed</span>'
                  : '<span class="ppct">'+Math.round(e.pct)+'%</span>';
      h+='<div class="prow"><span class="pdot '+cls+'"></span><span class="pname"><b>'+esc(e.name)+'</b><small>'+esc(e.label||'')+'</small></span>'+right+'</div>';
    }
    h+='</div>';
    body.innerHTML=h;
  }
  function updateBubble(){
    const list=Object.values(engines), run=list.filter(e=>e.state==='run'||e.state==='done');
    if(!list.length){ el('bTitle').textContent='Genesis — idle'; el('bBarWrap').style.display='none'; return; }
    const avg = Math.round(list.reduce((a,e)=>a+(e.pct||0),0)/list.length);
    const active=list.filter(e=>e.state==='run').length, done=list.filter(e=>e.state==='done').length;
    el('bTitle').textContent = session.stage==='finished'?'Genesis — done':'Working…';
    el('bSub').textContent = avg+'% · '+done+'/'+list.length+' engines';
    el('bBarWrap').style.display='block'; el('bBar').style.width=avg+'%';
  }
  function setStage(s){ session.stage=s; el('cStage').textContent=s; }

  function showApproval(d){
    const feed=el('chatFeed');
    const div=document.createElement('div');
    div.className='approve';
    div.innerHTML='<h4>⚠ Approval required</h4><div>'+esc(d.detail||d.gate||'Genesis needs your OK before continuing.')+'</div>'+
      '<div class="row"><button class="qbtn" style="border-color:var(--accent);color:var(--accent)" onclick="Companion.approve(true)">Approve</button>'+
      '<button class="qbtn" onclick="Companion.approve(false)">Deny</button></div>';
    feed.appendChild(div); scroll();
    if(!el('panel').classList.contains('open')) expand(); // auto-open on approval
  }

  function botMsg(txt){ const f=el('chatFeed'); const d=document.createElement('div'); d.className='msg bot'; d.innerHTML='<div class="who">Genesis</div>'+esc(txt); f.appendChild(d); scroll(); }
  function userMsg(txt){ const f=el('chatFeed'); const d=document.createElement('div'); d.className='msg user'; d.textContent=txt; f.appendChild(d); scroll(); }
  function scroll(){ const b=el('v-chat').parentElement; b.scrollTop=b.scrollHeight; }
  function esc(s){ const d=document.createElement('div'); d.textContent=String(s==null?'':s); return d.innerHTML; }

  function send(){
    const inp=el('input'), txt=inp.value.trim(); if(!txt)return; inp.value='';
    userMsg(txt);
    if(ws && ws.readyState===1){ ws.send(JSON.stringify({type:'user.intent',data:{text:txt}})); botMsg('On it — routing to the right engines. Watch Status for live progress.'); }
    else{ botMsg('Offline — start the engine with <code>genesis companion</code>, then I\'ll run this live. (Your message is not lost.)'); }
  }
  function approve(ok){ if(ws&&ws.readyState===1){ ws.send(JSON.stringify({type:'user.approval',data:{approved:ok}})); } botMsg(ok?'Approved.':'Denied.'); }
  function act(a){ el('input').value=a.intent; tab('chat'); send(); }
  function setLevel(l){ level=l; document.querySelectorAll('#levels .lvl').forEach(x=>x.classList.toggle('on',x.dataset.lvl===l)); if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'user.intent',data:{text:'set activity level '+l}})); }
  function theme(t){ document.documentElement.setAttribute('data-theme', t==='dark'?'dark':''); }

  function expand(){ el('bubble').classList.add('hidden'); el('panel').classList.add('open'); el('input').focus(); }
  function collapse(){ el('panel').classList.remove('open'); el('bubble').classList.remove('hidden'); }
  function canvas(){ botMsg('Opening the Canvas for deep analysis…'); if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'user.intent',data:{text:'open canvas'}})); }
  function tab(v){ document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v)); document.querySelectorAll('.view').forEach(x=>x.classList.remove('on')); el('v-'+v).classList.add('on'); }

  function initActions(){ const g=el('qaGrid'); ACTIONS.forEach(a=>{ const b=document.createElement('button'); b.className='qbtn'; b.innerHTML='<span class="qi">'+a.icon+'</span>'+a.label; b.onclick=()=>act(a); g.appendChild(b); }); }

  document.addEventListener('DOMContentLoaded', ()=>{ if(cfg.theme==='dark')theme('dark'); initActions(); connect(); });
  return {expand,collapse,tab,send,approve,setLevel,theme,canvas};
})();
</script>
</body>
</html>"""
