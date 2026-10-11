#!/usr/bin/env python3
"""Generate 7 faithful landing pages, one per source, from extracted DNA."""
import pathlib

OUT = pathlib.Path(__file__).parent

# DNA extracted live from each source via Playwright computed styles.
SOURCES = {
"raycast": dict(
  name="Raycast", mode="dark",
  bg="#07080a", bg2="#0f1117", surface="rgba(255,255,255,.04)", surfaceB="rgba(255,255,255,.08)",
  text="#ffffff", t2="#9da2ad", t3="#6a6e7a", line="rgba(255,255,255,.08)",
  accent="#0083FE", accentText="#0083FE",
  font="'Inter',-apple-system,sans-serif", mono="'JetBrains Mono',monospace",
  h1size="64px", h1lh="70px", h1weight="600", h1ls="-1px",
  # Raycast's primary button is WHITE, not accent
  btnBg="#e6e6e6", btnColor="#2f3031", btnRadius="8px", btnPad="10px 18px", btnFw="500",
  glow=True, fontImport="Inter:wght@400;500;600;700",
),
"supabase": dict(
  name="Supabase", mode="light",
  bg="#fcfcfc", bg2="#f8f8f6", surface="#ffffff", surfaceB="#ececec",
  text="#171717", t2="#5b5b5b", t3="#a0a0a0", line="#ededed",
  accent="#3fcf8e", accentText="#1a8f5e",
  font="'Inter',sans-serif", mono="'JetBrains Mono',monospace",
  h1size="48px", h1lh="50px", h1weight="500", h1ls="-1.5px",
  btnBg="#3fcf8e", btnColor="#171717", btnRadius="6px", btnPad="10px 18px", btnFw="500",
  glow=False, fontImport="Inter:wght@400;500;600",
),
"railway": dict(
  name="Railway", mode="dark",
  bg="#13111c", bg2="#1a1826", surface="#20202e", surfaceB="rgba(255,255,255,.09)",
  text="#ffffff", t2="#a09db5", t3="#6e6b82", line="rgba(255,255,255,.07)",
  accent="#9d6bff", accentText="#b794ff",
  font="'Inter',-apple-system,sans-serif", mono="'JetBrains Mono',monospace",
  h1size="54px", h1lh="60px", h1weight="600", h1ls="-1.96px",
  btnBg="#9d6bff", btnColor="#fff", btnRadius="4px", btnPad="11px 18px", btnFw="600",
  glow=True, fontImport="Inter:wght@400;500;600;700",
),
"prisma": dict(
  name="Prisma", mode="light",
  bg="#ffffff", bg2="#f7f8fa", surface="#f7f8fa", surfaceB="#e2e8f0",
  text="#1d242f", t2="#4a5568", t3="#94a0b2", line="#e8ecf1",
  accent="#5a67d8", accentText="#4a55c8",
  font="'Inter',sans-serif", mono="'JetBrains Mono',monospace",
  h1size="52px", h1lh="58px", h1weight="800", h1ls="-1px",
  btnBg="#5a67d8", btnColor="#fff", btnRadius="3px", btnPad="11px 18px", btnFw="700",
  glow=False, fontImport="Inter:wght@400;500;700;800",
),
"bun": dict(
  name="Bun", mode="dark",
  bg="#14151a", bg2="#1c1d24", surface="rgba(255,255,255,.03)", surfaceB="rgba(255,255,255,.08)",
  text="#ffffff", t2="#b6b9c2", t3="#6e7079", line="rgba(255,255,255,.07)",
  accent="#f472b6", accentText="#f99bcf",
  font="system-ui,-apple-system,sans-serif", mono="'JetBrains Mono',monospace",
  h1size="56px", h1lh="58px", h1weight="800", h1ls="-1.5px",
  btnBg="#f472b6", btnColor="#14151a", btnRadius="8px", btnPad="12px 20px", btnFw="600",
  glow=False, fontImport="JetBrains+Mono:wght@400;500",
),
"mercury": dict(
  name="Mercury", mode="light",
  bg="#faf9f7", bg2="#f2f1 ed", surface="#ffffff", surfaceB="#e7e5e0",
  text="#1c1a24", t2="#5a5766", t3="#9a96a6", line="#eceae4",
  accent="#5468d4", accentText="#4456c0",
  font="'Newsreader',Georgia,serif", mono="'JetBrains Mono',monospace",
  h1size="60px", h1lh="64px", h1weight="400", h1ls="-1px",
  btnBg="#28253b", btnColor="#edecfb", btnRadius="40px", btnPad="13px 26px", btnFw="500",
  glow=False, fontImport="Newsreader:ital,opsz,wght@0,6..72,400..600;1,6..72,400",
  serifHero=True,
),
"clerk": dict(
  name="Clerk", mode="light",
  bg="#f7f7f8", bg2="#ffffff", surface="#ffffff", surfaceB="#e6e6ea",
  text="#131316", t2="#5e6068", t3="#9a9ca4", line="#ececef",
  accent="#6c47ff", accentText="#5a37e0",
  font="'Inter',sans-serif", mono="'JetBrains Mono',monospace",
  h1size="48px", h1lh="56px", h1weight="700", h1ls="-1.2px",
  btnBg="#42434d", btnColor="#fff", btnRadius="6px", btnPad="10px 18px", btnFw="500",
  glow=False, fontImport="Inter:wght@400;500;600;700",
),
}

TEMPLATE = """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Genesis Architect</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={fontImport}&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:{bg};--bg2:{bg2};--surface:{surface};--sb:{surfaceB};--t1:{text};--t2:{t2};--t3:{t3};
--line:{line};--accent:{accent};--at:{accentText};--font:{font};--mono:{mono}}}
*{{margin:0;padding:0;box-sizing:border-box}}
::selection{{background:var(--accent);color:#fff}}
body{{font-family:var(--font);background:var(--bg);color:var(--t1);line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}}
.mono{{font-family:var(--mono)}}
a{{color:inherit;text-decoration:none}}
{glowCss}
.page{{position:relative;z-index:1;max-width:1080px;margin:0 auto;padding:0 28px}}
.rv{{opacity:0;transform:translateY(16px);transition:opacity .75s cubic-bezier(.2,.7,.2,1),transform .75s cubic-bezier(.2,.7,.2,1)}}
.rv.in{{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){{.rv{{opacity:1;transform:none}}}}
.btn{{display:inline-flex;align-items:center;gap:8px;font-weight:{btnFw};font-size:14.5px;padding:{btnPad};border-radius:{btnRadius};cursor:pointer;transition:.16s;border:1px solid transparent}}
.btn svg{{width:15px;height:15px}}
.btn.p{{background:{btnBg};color:{btnColor}}}.btn.p:hover{{filter:brightness(1.08);transform:translateY(-1px)}}
.btn.g{{background:var(--surface);border-color:var(--sb);color:var(--t1)}}.btn.g:hover{{border-color:var(--accent)}}
a:focus-visible,.btn:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
.nav{{display:flex;align-items:center;justify-content:space-between;height:74px;position:sticky;top:0;z-index:40;background:{navBg};backdrop-filter:blur(12px);border-bottom:1px solid var(--line);margin:0 -28px;padding:0 28px}}
.nav img{{height:50px{logoFilter}}}
.nav .menu{{display:flex;gap:26px;align-items:center}}.nav .menu a.l{{font-size:14px;color:var(--t2)}}.nav .menu a.l:hover{{color:var(--t1)}}
@media(max-width:760px){{.nav .menu a.l{{display:none}}}}
.hero{{text-align:center;padding:92px 0 28px}}
.pill{{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--at);background:color-mix(in srgb,var(--accent) 10%,transparent);border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);padding:6px 14px;border-radius:99px;margin-bottom:26px;font-family:var(--mono)}}
.pill .d{{width:6px;height:6px;border-radius:50%;background:var(--accent)}}
h1{{font-size:{h1size};line-height:{h1lh};font-weight:{h1weight};letter-spacing:{h1ls};max-width:15ch;margin:0 auto}}
@media(max-width:680px){{h1{{font-size:38px;line-height:42px}}}}
.hero .sub{{font-size:20px;color:var(--t2);max-width:52ch;margin:24px auto 0;{subFont}}}
.hero .cta{{margin-top:32px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap}}
.hero .inst{{margin-top:18px;font-family:var(--mono);font-size:13px;color:var(--t3)}}
.termwrap{{max-width:780px;margin:52px auto 0}}
.term{{background:{termBg};border:1px solid var(--sb);border-radius:14px;overflow:hidden;box-shadow:0 30px 70px rgba(0,0,0,{termShadow});text-align:left}}
.term .bar{{display:flex;gap:7px;align-items:center;padding:13px 16px;border-bottom:1px solid var(--line)}}
.term .bar i{{width:11px;height:11px;border-radius:50%}}.term .bar .r{{background:#ff5f57}}.term .bar .y{{background:#febc2e}}.term .bar .g{{background:#28c840}}
.term .bar span{{margin-left:8px;font-family:var(--mono);font-size:12px;color:#6b7280}}
.term .body{{padding:22px;font-family:var(--mono);font-size:13px;line-height:1.95;color:#c9ced8;white-space:pre-wrap;min-height:250px}}
.term .body .pr{{color:var(--at)}}.term .body .o{{color:#8b92a3}}.term .body .ok{{color:#4ade80}}.term .body .w{{color:#fbbf24}}
.cur{{display:inline-block;width:7px;height:14px;background:var(--at);vertical-align:-2px;animation:bl 1s steps(1) infinite}}
@keyframes bl{{50%{{opacity:0}}}}
section{{padding:84px 0;position:relative;z-index:1}}
.lab{{font-family:var(--mono);font-size:12.5px;color:var(--at);letter-spacing:.07em;text-transform:uppercase}}
h2{{font-size:{h2size};font-weight:{h2weight};letter-spacing:-.025em;margin-top:12px;max-width:18ch;line-height:1.1}}
.sub2{{color:var(--t2);font-size:18px;margin-top:12px;max-width:50ch;{subFont}}}
.cards{{margin-top:42px;display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}@media(max-width:780px){{.cards{{grid-template-columns:1fr}}}}
.c{{background:var(--surface);border:1px solid var(--line);border-radius:{cardRadius};padding:28px;transition:.2s}}
.c:hover{{border-color:var(--sb);transform:translateY(-3px)}}
.c .ic{{width:44px;height:44px;border-radius:{icRadius};background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--at);display:flex;align-items:center;justify-content:center;margin-bottom:16px}}
.c .ic svg{{width:22px;height:22px}}.c h3{{font-size:19px;font-weight:{h3weight};margin-bottom:7px}}.c p{{color:var(--t2);font-size:14.5px;{bodyFont}}}
.cmpwrap{{margin-top:42px;border:1px solid var(--sb);border-radius:14px;overflow:hidden}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:500;padding:16px;background:var(--surface);border-bottom:1px solid var(--sb)}}
th:nth-child(2),th:nth-child(3){{text-align:center;width:108px}}th:nth-child(3){{color:var(--at)}}
td{{padding:14px 16px;border-top:1px solid var(--line);font-size:14.5px}}td:first-child{{color:var(--t1)}}td:nth-child(2),td:nth-child(3){{text-align:center}}
tr:hover td{{background:var(--surface)}}.y{{color:var(--at)}}.n{{color:var(--t3)}}
.pg{{margin-top:42px;display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:820px;margin-left:auto;margin-right:auto}}@media(max-width:680px){{.pg{{grid-template-columns:1fr}}}}
.pl{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:34px}}
.pl.pro{{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}}
.pl .bdg{{display:inline-block;font-family:var(--mono);font-size:11px;color:var(--at);background:color-mix(in srgb,var(--accent) 12%,transparent);padding:5px 10px;border-radius:99px;margin-bottom:14px}}
.pl .pn{{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--t3)}}
.pl .amt{{font-size:46px;font-weight:{h2weight};letter-spacing:-1.5px;margin:12px 0 2px;line-height:1}}.pl .amt span{{font-size:14.5px;color:var(--t2);font-weight:400}}
.pl .alt{{color:var(--t3);font-size:14px;margin-bottom:20px}}
.pl ul{{list-style:none;margin:0 0 24px;display:flex;flex-direction:column;gap:10px}}.pl li{{font-size:14.5px;display:flex;gap:10px}}.pl li .x{{color:var(--at)}}
.pl .btn{{width:100%;justify-content:center}}.pl .stk{{display:flex;flex-direction:column;gap:10px}}
footer{{border-top:1px solid var(--line);padding:34px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px}}
footer img{{height:34px{logoFilter}}}footer .fl{{font-family:var(--mono);font-size:12px;color:var(--t3)}}
footer .links a{{font-size:14px;color:var(--t2);margin-left:20px}}footer .links a:hover{{color:var(--t1)}}
</style></head><body>
{glowEl}
<div class="page">
<header class="nav"><a href="#top"><img src="assets/logo{logoVar}.png" alt="Genesis Architect"></a>
<div class="menu"><a class="l" href="#how">How it works</a><a class="l" href="#cmp">Free / Pro</a><a class="l" href="#pricing">Pricing</a><a class="l" href="https://github.com/maioio/genesis-architect">GitHub</a><a class="btn p" href="#pricing" style="padding:9px 16px;font-size:13px">Get Pro</a></div></header>
<section class="hero" id="top">
<span class="pill rv"><span class="d"></span>open-core developer tool · v5.4</span>
<h1 class="rv">It finds the bug before you write it.</h1>
<p class="sub rv">Genesis reads the issues other developers already closed, then builds the fix into your project on day zero.</p>
<div class="cta rv"><a class="btn p" href="#pricing">Get Pro &mdash; $9/mo
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg></a>
<a class="btn g" href="https://github.com/maioio/genesis-architect">View source</a></div>
<div class="inst rv">$ pip install genesis-architect</div>
<div class="termwrap rv"><div class="term"><div class="bar"><i class="r"></i><i class="y"></i><i class="g"></i><span>~/code &middot; genesis</span></div>
<div class="body" id="tt"></div></div></div>
</section>
<section id="how"><span class="lab rv">How it works</span><h2 class="rv">Built on real failures, not guesses.</h2>
<div class="cards">
<div class="c rv"><div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg></div><h3>Real failures</h3><p>Mines actual GitHub issues from similar repos. Every pitfall is cited and CI-verified live.</p></div>
<div class="c rv"><div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3 6 6 .9-4.5 4.3 1 6.3L12 17l-5.5 2.8 1-6.3L3 8.9 9 8z"/></svg></div><h3>Fixes built in</h3><p>Mitigations wired into the scaffold, not appended as a checklist you'll scroll past.</p></div>
<div class="c rv"><div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h7l-1 8 10-12h-7z"/></svg></div><h3>Zero stubs</h3><p>Idea to a running, tested project in minutes. Twelve real files, not a folder of TODOs.</p></div>
</div></section>
<section id="cmp"><span class="lab rv">Free vs Pro</span><h2 class="rv">The free core is the whole tool.</h2><p class="sub2 rv">Pro adds the multi-source research engine. Start free, upgrade for the whole internet.</p>
<div class="cmpwrap rv"><table><thead><tr><th>Capability</th><th>Free</th><th>Pro</th></tr></thead><tbody id="tb"></tbody></table></div></section>
<section id="pricing"><div style="text-align:center"><span class="lab rv">Pricing</span><h2 class="rv" style="margin-left:auto;margin-right:auto">Founder's price. First 50, locked for life.</h2><p class="sub2 rv" style="margin-left:auto;margin-right:auto">After 50 seats it goes to $19/mo. Early supporters never pay more.</p></div>
<div class="pg">
<div class="pl rv"><div class="pn">Free</div><div class="amt">$0 <span>/ forever</span></div><div class="alt">The complete scaffolder.</div>
<ul><li><span class="x">+</span> Full scaffolder &middot; Python, TS, Go, Rust</li><li><span class="x">+</span> CI/CD &amp; security defaults</li><li><span class="x">+</span> Top 3 GitHub pitfalls per project</li></ul>
<a class="btn g" href="https://github.com/maioio/genesis-architect">Install free</a></div>
<div class="pl pro rv"><span class="bdg">FIRST 50 &middot; LOCKED FOR LIFE</span><div class="pn">Pro</div><div class="amt">$9 <span>/ month</span></div><div class="alt">or $90/yr &mdash; two months free.</div>
<ul><li><span class="x">+</span> Everything in Free</li><li><span class="x">+</span> Multi-source research (GitHub, Reddit, YouTube, IG)</li><li><span class="x">+</span> Cross-source ranking + video-to-pitfall</li><li><span class="x">+</span> CVE validation + cross-session memory</li><li><span class="x">+</span> Recovery scan</li></ul>
<div class="stk"><a class="btn p" href="https://eshetmaio.gumroad.com/l/dduhm">Subscribe &mdash; $9/mo</a><a class="btn g" href="https://eshetmaio.gumroad.com/l/kzbpct">Yearly &mdash; $90</a></div></div>
</div></section>
<footer><div class="fl">&copy; 2026 &middot; open-core &middot; built by maio eshet &middot; haters &gt; /dev/null</div>
<div class="links"><a href="https://github.com/maioio/genesis-architect">GitHub</a><a href="https://eshetmaio.gumroad.com/l/kzbpct">Buy Pro</a><a href="mailto:maio.eshet@gmail.com">Contact</a></div></footer>
</div>
<script>
var Y='<span class="y">&#9679;</span>',N='<span class="n">&mdash;</span>';
var r=[["Full scaffolder (Python, TS, Go, Rust)",1,1],["CI/CD, security defaults, templates",1,1],["Top 3 GitHub pitfalls per project",1,1],["Multi-source research (GitHub, Reddit, YouTube, IG)",0,1],["Cross-source pitfall ranking",0,1],["Video-to-pitfall extraction",0,1],["Package-registry + CVE validation",0,1],["Cross-session memory",0,1],["Recovery scan for existing codebases",0,1]];
document.getElementById('tb').innerHTML=r.map(function(x){{return '<tr><td>'+x[0]+'</td><td>'+(x[1]?Y:N)+'</td><td>'+(x[2]?Y:N)+'</td></tr>'}}).join('');
var io=new IntersectionObserver(function(es){{es.forEach(function(e){{if(e.isIntersecting){{e.target.classList.add('in');io.unobserve(e.target)}}}})}},{{threshold:.12}});
document.querySelectorAll('.rv').forEach(function(el,i){{el.style.transitionDelay=(Math.min(i,6)*45)+'ms';io.observe(el)}});
var lines=[{{t:'$ genesis init "a python cli for logs"',c:'pr',d:32}},{{t:'→ scanning 18 similar repos on github...',c:'o',d:13}},{{t:'→ mining closed issues for failures...',c:'o',d:13}},{{t:'✓ 4 confirmed pitfalls found',c:'ok',d:16}},{{t:'! path traversal — seen in 3/5 repos',c:'w',d:14}},{{t:'! logic in cli callback (untestable)',c:'w',d:14}},{{t:'→ scaffolding with mitigations...',c:'o',d:13}},{{t:'✓ ready · 12 files · 0 empty stubs',c:'ok',d:18}}];
var el=document.getElementById('tt');function esc(s){{return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}}
function run(){{el.innerHTML='';var li=0;function line(){{if(li>=lines.length){{var c=document.createElement('span');c.className='cur';el.appendChild(c);return}}var L=lines[li],sp=document.createElement('div');sp.className=L.c;el.appendChild(sp);var i=0;(function ch(){{if(i<=L.t.length){{sp.innerHTML=esc(L.t.slice(0,i));i++;setTimeout(ch,L.d)}}else{{li++;setTimeout(line,li===1?240:130)}}}})();}}line();}}
if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches){{el.innerHTML=lines.map(function(L){{return '<div class="'+L.c+'">'+esc(L.t)+'</div>'}}).join('')}}else{{setTimeout(run,500)}}
</script></body></html>"""

for key, d in SOURCES.items():
    dark = d["mode"] == "dark"
    ctx = dict(d)
    ctx["h2size"] = "40px"; ctx["h2weight"] = d["h1weight"]; ctx["h3weight"] = "600"
    ctx["navBg"] = ("rgba(7,8,12,.7)" if dark else "rgba(255,255,255,.8)")
    ctx["logoFilter"] = (";filter:brightness(0) invert(1)" if dark else "")
    ctx["logoVar"] = ("_white" if dark else "")
    ctx["termBg"] = "#0e1320" if not dark else d["bg2"]
    ctx["termShadow"] = ".5" if dark else ".16"
    ctx["cardRadius"] = d["btnRadius"]; ctx["icRadius"] = d["btnRadius"]
    ctx["serifHero"] = d.get("serifHero", False)
    ctx["subFont"] = "font-family:var(--font)" if d.get("serifHero") else ""
    ctx["bodyFont"] = ""
    if d["glow"]:
        ctx["glowCss"] = ".glow{position:fixed;top:-240px;left:50%;transform:translateX(-50%);width:960px;height:540px;z-index:0;pointer-events:none;background:radial-gradient(closest-side,color-mix(in srgb,var(--accent) 20%,transparent),transparent 70%);filter:blur(24px)}"
        ctx["glowEl"] = '<div class="glow"></div>'
    else:
        ctx["glowCss"] = ""; ctx["glowEl"] = ""
    html = TEMPLATE.format(**ctx)
    (OUT / f"{key}.html").write_text(html, encoding="utf-8")
    print(f"built {key}.html")
print("done")
