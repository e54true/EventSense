#!/usr/bin/env python3
"""Build a self-contained, study-optimized HTML from LEARNING.md.

- markdown -> HTML (tables, fenced code, toc) with Pygments (monokai) highlight
- bs4 post-process: callout cards (通則/面試/⚠️/📝), heading anchors, table wrap
- inline CSS+JS template: sticky collapsible TOC + scroll-spy, dark/light,
  TOC search, reading progress, back-to-top, and a 復習模式 (review mode that
  shows only headings + key cards + 速記表 tables for memorization).
No CDN — opens offline anywhere.
"""
import os
import re
import sys

import markdown
from bs4 import BeautifulSoup
from pygments.formatters import HtmlFormatter

# Usage: build_learning_html.py [SRC.md] [OUT.html] ["Title"]
SRC = sys.argv[1] if len(sys.argv) > 1 else "/Users/lokiboom/Desktop/EventSense/LEARNING.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(SRC)[0] + ".html"

md_text = open(SRC, encoding="utf-8").read()

md = markdown.Markdown(
    extensions=["extra", "toc", "sane_lists", "codehilite"],
    extension_configs={
        "toc": {"toc_depth": "1-3"},
        "codehilite": {"guess_lang": False, "css_class": "codehilite"},
    },
)
body_html = md.convert(md_text)
toc_tokens = md.toc_tokens

# --- post-process ---
soup = BeautifulSoup(body_html, "html.parser")

# callout classes on blockquotes (priority: warn > note > interview > tip)
for bq in soup.find_all("blockquote"):
    t = bq.get_text()
    cls = None
    if "⚠️" in t:
        cls = "warn"
    elif "📝" in t:
        cls = "note"
    elif "面試" in t:
        cls = "interview"
    elif any(k in t for k in ("狀態", "目標", "TL;DR", "驗收狀態")):
        cls = "meta"
    elif "通則" in t:
        cls = "tip"
    if cls:
        bq["class"] = bq.get("class", []) + ["callout", cls]

# heading anchors
for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
    hid = tag.get("id")
    if not hid:
        continue
    a = soup.new_tag("a", href="#" + hid)
    a["class"] = ["anchor"]
    a.string = "#"
    tag.append(a)

# wrap tables for horizontal scroll
for table in soup.find_all("table"):
    wrap = soup.new_tag("div")
    wrap["class"] = ["table-wrap"]
    table.insert_before(wrap)
    wrap.append(table.extract())

content_html = str(soup)

# --- TOC build from toc_tokens ---
def render_children(children):
    if not children:
        return ""
    out = ['<ul class="toc-children">']
    for c in children:
        lvl = c["level"]
        out.append(f'<li class="toc-l{lvl}"><a href="#{c["id"]}">{c["name"]}</a>')
        out.append(render_children(c.get("children", [])))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)

# Adaptive nav: if the doc has multiple h1 (LEARNING-style "Parts"), the first
# h1 is the title and the rest are collapsible nav groups. If it has a single
# h1 (IMPLEMENTATION_LOG-style flat doc), promote that h1's h2 children to be
# the nav groups so the milestones are still navigable.
title_node = toc_tokens[0] if toc_tokens else None
if len(toc_tokens) > 1:
    nav_nodes = toc_tokens[1:]
elif title_node:
    nav_nodes = title_node.get("children", [])
else:
    nav_nodes = []

toc_parts = []
if title_node:
    toc_parts.append(
        f'<li class="toc-top"><a href="#{title_node["id"]}">{title_node["name"]}</a></li>'
    )
for tok in nav_nodes:
    kids = render_children(tok.get("children", []))
    toggle = '<button class="toc-toggle" aria-label="toggle">▸</button>' if kids else '<span class="toc-toggle-spacer"></span>'
    toc_parts.append(
        f'<li class="toc-part">'
        f'<div class="toc-part-row">{toggle}'
        f'<a class="toc-part-link" href="#{tok["id"]}">{tok["name"]}</a></div>'
        f'{kids}</li>'
    )
toc_html = '<ul class="toc-root">' + "".join(toc_parts) + "</ul>"

pyg_css = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

title = sys.argv[3] if len(sys.argv) > 3 else (title_node["name"] if title_node else "EventSense")


# header meta counts (adaptive to the nav structure)
def _count_all(nodes):
    return sum(1 + _count_all(n.get("children", [])) for n in nodes)


n_parts = len(nav_nodes)
n_secs = _count_all(nav_nodes)

CSS = r"""
:root{
  --bg:#fbfaf7; --fg:#23201c; --muted:#6b6459; --line:#e7e1d6; --card:#ffffff;
  --accent:#b4530a; --accent2:#7c4dff;
  --tip-bg:#eef7ee; --tip-bd:#3f9142; --note-bg:#eef3fb; --note-bd:#3b76c9;
  --warn-bg:#fdf1e7; --warn-bd:#d9730d; --intv-bg:#f3effc; --intv-bd:#7c4dff;
  --meta-bg:#f1f4f3; --meta-bd:#5a8a86;
  --sidebar:#f4f0e8; --sidebar-fg:#3a352e; --hit:#fff3d6;
  --code-bg:#272822;
}
[data-theme=dark]{
  --bg:#16181d; --fg:#d6d3cd; --muted:#8d8f95; --line:#2c2f36; --card:#1d2026;
  --accent:#ff9d52; --accent2:#b39dff;
  --tip-bg:#16241a; --tip-bd:#3f9142; --note-bg:#152234; --note-bd:#4b86d6;
  --warn-bg:#2a1d12; --warn-bd:#d9730d; --intv-bg:#211a33; --intv-bd:#9a7bff;
  --meta-bg:#16211f; --meta-bd:#5a8a86;
  --sidebar:#1b1e24; --sidebar-fg:#c2bfb8; --hit:#3a3320; --code-bg:#1e1f1a;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  font-size:17px;line-height:1.85;-webkit-font-smoothing:antialiased;}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* top bar */
#topbar{position:fixed;top:0;left:0;right:0;height:54px;z-index:50;display:flex;align-items:center;gap:10px;
  padding:0 14px;background:var(--card);border-bottom:1px solid var(--line);}
#topbar .brand{font-weight:700;color:var(--accent);white-space:nowrap;font-size:15px}
#topbar .meta{color:var(--muted);font-size:12px;white-space:nowrap}
#topbar .spacer{flex:1}
#search{flex:0 1 260px;max-width:260px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;
  background:var(--bg);color:var(--fg);font-size:13px}
.btn{cursor:pointer;border:1px solid var(--line);background:var(--bg);color:var(--fg);
  border-radius:8px;padding:7px 11px;font-size:13px;white-space:nowrap}
.btn:hover{border-color:var(--accent)}
.btn.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#progress{position:fixed;top:54px;left:0;height:3px;background:var(--accent);width:0;z-index:51;transition:width .1s}
#menuBtn{display:none}

/* layout */
.layout{display:flex;padding-top:54px}
#sidebar{width:330px;flex:none;position:sticky;top:54px;height:calc(100vh - 54px);overflow:auto;
  background:var(--sidebar);color:var(--sidebar-fg);border-right:1px solid var(--line);padding:14px 6px 60px}
#content{flex:1;min-width:0;max-width:880px;margin:0 auto;padding:28px 36px 120px}

/* TOC */
#toc ul{list-style:none;margin:0;padding:0}
#toc .toc-root>li{margin:1px 0}
.toc-top a{display:block;padding:6px 10px;font-weight:700;color:var(--accent)}
.toc-part-row{display:flex;align-items:flex-start;gap:2px}
.toc-toggle{flex:none;width:22px;height:26px;line-height:24px;border:0;background:none;color:var(--muted);
  cursor:pointer;font-size:11px;transition:transform .15s;padding:0}
.toc-part.open>.toc-part-row .toc-toggle{transform:rotate(90deg)}
.toc-toggle-spacer{display:inline-block;width:22px}
.toc-part-link{display:block;padding:5px 6px;font-weight:600;font-size:14px;color:var(--sidebar-fg);flex:1}
.toc-children{display:none;margin-left:22px!important;border-left:1px solid var(--line);padding-left:6px!important}
.toc-part.open>.toc-children{display:block}
.toc-children a{display:block;padding:3px 8px;font-size:12.5px;color:var(--muted);border-radius:6px}
.toc-l3 a{font-size:12px;opacity:.85;padding-left:14px}
#toc a:hover{background:var(--hit);text-decoration:none;color:var(--fg)}
#toc a.active{background:var(--accent);color:#fff;font-weight:600}
.toc-hidden{display:none!important}

/* content typography */
#content h1{font-size:30px;line-height:1.3;margin:46px 0 10px;padding-bottom:10px;
  border-bottom:3px solid var(--accent);color:var(--accent)}
#content h1:first-child{margin-top:0}
#content h2{font-size:23px;margin:38px 0 8px;padding-left:11px;border-left:5px solid var(--accent)}
#content h3{font-size:19px;margin:28px 0 6px;color:var(--fg)}
#content h4{font-size:16px;margin:20px 0 4px;color:var(--muted)}
#content :is(h1,h2,h3,h4){scroll-margin-top:66px;position:relative}
#content p{margin:12px 0}
#content ul,#content ol{margin:10px 0;padding-left:26px}
#content li{margin:5px 0}
#content hr{border:0;border-top:1px dashed var(--line);margin:34px 0}
#content strong{color:var(--fg);font-weight:700}
[data-theme=dark] #content strong{color:#fff}
.anchor{margin-left:8px;color:var(--muted);opacity:0;font-weight:400;text-decoration:none;font-size:.7em}
:is(h1,h2,h3,h4):hover .anchor{opacity:.6}
.anchor:hover{opacity:1!important;text-decoration:none}

/* inline + block code */
:not(pre)>code{background:var(--hit);padding:.1em .4em;border-radius:5px;font-size:.86em;
  font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.codehilite{background:var(--code-bg);border-radius:10px;margin:14px 0;overflow:auto;border:1px solid rgba(0,0,0,.25)}
.codehilite pre{margin:0;padding:14px 16px;overflow:auto;font-size:13.5px;line-height:1.6;
  font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* tables */
.table-wrap{overflow-x:auto;margin:14px 0;border:1px solid var(--line);border-radius:10px}
#content table{border-collapse:collapse;width:100%;font-size:14.5px}
#content th,#content td{border-bottom:1px solid var(--line);padding:9px 13px;text-align:left;vertical-align:top}
#content th{background:var(--sidebar);font-weight:700;white-space:nowrap}
#content tbody tr:nth-child(even){background:rgba(127,127,127,.05)}

/* callouts */
blockquote{margin:14px 0;padding:11px 16px;border-left:5px solid var(--line);background:var(--card);border-radius:0 8px 8px 0}
blockquote p{margin:6px 0}
blockquote.callout{position:relative}
blockquote.tip{border-color:var(--tip-bd);background:var(--tip-bg)}
blockquote.note{border-color:var(--note-bd);background:var(--note-bg)}
blockquote.warn{border-color:var(--warn-bd);background:var(--warn-bg)}
blockquote.interview{border-color:var(--intv-bd);background:var(--intv-bg)}
blockquote.meta{border-color:var(--meta-bd);background:var(--meta-bg)}
blockquote.callout::before{font-size:11px;font-weight:700;letter-spacing:.5px;display:block;
  margin-bottom:3px;opacity:.9}
blockquote.tip::before{content:"通則 / RULE";color:var(--tip-bd)}
blockquote.note::before{content:"📝 後續更新 / NOTE";color:var(--note-bd)}
blockquote.warn::before{content:"⚠️ 注意 / GOTCHA";color:var(--warn-bd)}
blockquote.interview::before{content:"🎤 面試重點";color:var(--intv-bd)}
blockquote.meta::before{content:"📍 里程碑";color:var(--meta-bd)}

/* back to top */
#totop{position:fixed;right:22px;bottom:22px;z-index:40;display:none;
  border-radius:50%;width:46px;height:46px;font-size:18px;border:1px solid var(--line);
  background:var(--card);color:var(--accent);cursor:pointer;box-shadow:0 3px 12px rgba(0,0,0,.15)}

/* review mode: keep headings, callouts, tables, lists; hide prose + code */
body.review #content p:not(.keep),
body.review #content pre,
body.review #content .codehilite,
body.review #content blockquote:not(.callout){display:none}
body.review #content :is(ul,ol){opacity:.95}
#reviewHint{display:none;margin:0 0 18px;padding:9px 14px;border-radius:8px;background:var(--intv-bg);
  border:1px solid var(--intv-bd);font-size:13px;color:var(--muted)}
body.review #reviewHint{display:block}

@media (max-width:880px){
  #menuBtn{display:inline-block}
  #sidebar{position:fixed;left:0;top:54px;z-index:45;transform:translateX(-100%);transition:transform .2s;
    width:84%;max-width:340px;box-shadow:4px 0 18px rgba(0,0,0,.2)}
  #sidebar.open{transform:none}
  #content{padding:20px 18px 100px}
  #search{flex-basis:120px}
  #topbar .meta{display:none}
}
"""

JS = r"""
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
// theme
const root=document.documentElement;
function setTheme(t){root.setAttribute('data-theme',t);localStorage.setItem('es-theme',t);
  $('#themeBtn').textContent=t==='dark'?'☀︎ 淺色':'☾ 深色';}
setTheme(localStorage.getItem('es-theme')|| (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'));
$('#themeBtn').onclick=()=>setTheme(root.getAttribute('data-theme')==='dark'?'light':'dark');
// review mode
function setReview(on){document.body.classList.toggle('review',on);$('#reviewBtn').classList.toggle('on',on);
  localStorage.setItem('es-review',on?'1':'');}
$('#reviewBtn').onclick=()=>setReview(!document.body.classList.contains('review'));
if(localStorage.getItem('es-review'))setReview(true);
// TOC collapse
$$('.toc-toggle').forEach(b=>b.onclick=e=>{e.preventDefault();b.closest('.toc-part').classList.toggle('open');});
$$('.toc-part-link, .toc-children a, .toc-top a').forEach(a=>a.addEventListener('click',()=>{
  if(window.innerWidth<=880)$('#sidebar').classList.remove('open');}));
// search filter
$('#search').addEventListener('input',e=>{
  const q=e.target.value.trim().toLowerCase();
  $$('#toc .toc-part').forEach(p=>{
    let any=false;
    p.querySelectorAll('a').forEach(a=>{
      const hit=!q||a.textContent.toLowerCase().includes(q);
      a.closest('li').classList.toggle('toc-hidden',!hit&&!a.classList.contains('toc-part-link'));
      if(hit)any=true;
    });
    const plHit=!q||p.querySelector('.toc-part-link').textContent.toLowerCase().includes(q);
    p.classList.toggle('toc-hidden',!any&&!plHit);
    if(q&&any)p.classList.add('open');
  });
});
// scroll-spy
const heads=$$('#content h1,#content h2,#content h3').filter(h=>h.id);
const linkFor={}; $$('#toc a').forEach(a=>{const id=a.getAttribute('href').slice(1);linkFor[id]=a;});
let ticking=false;
function spy(){
  ticking=false;
  const y=window.scrollY+80; let cur=heads[0];
  for(const h of heads){ if(h.offsetTop<=y)cur=h; else break; }
  if(!cur)return;
  $$('#toc a.active').forEach(a=>a.classList.remove('active'));
  const a=linkFor[cur.id];
  if(a){a.classList.add('active');
    const part=a.closest('.toc-part'); if(part)part.classList.add('open');
    a.scrollIntoView({block:'nearest'});}
  // progress
  const docH=document.documentElement.scrollHeight-window.innerHeight;
  $('#progress').style.width=(docH>0?(window.scrollY/docH*100):0)+'%';
  $('#totop').style.display=window.scrollY>500?'block':'none';
}
addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(spy);}},{passive:true});
addEventListener('load',spy);spy();
$('#totop').onclick=()=>scrollTo({top:0,behavior:'smooth'});
$('#menuBtn').onclick=()=>$('#sidebar').classList.toggle('open');
"""

HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__PYG__
__CSS__</style>
</head>
<body>
<div id="topbar">
  <button class="btn" id="menuBtn">☰</button>
  <span class="brand">📘 __TITLE__</span>
  <span class="meta">__META__</span>
  <span class="spacer"></span>
  <input id="search" placeholder="🔍 搜尋章節…" autocomplete="off">
  <button class="btn" id="reviewBtn" title="只顯示標題+重點卡+速記表">復習模式</button>
  <button class="btn" id="themeBtn">☾ 深色</button>
</div>
<div id="progress"></div>
<div class="layout">
  <aside id="sidebar"><nav id="toc">__TOC__</nav></aside>
  <main id="content">
    <div id="reviewHint">復習模式:只顯示標題、重點卡(通則/面試/⚠️/📝)與表格。再按一次「復習模式」看全文。</div>
    __CONTENT__
  </main>
</div>
<button id="totop" title="回頂端">↑</button>
<script>__JS__</script>
</body>
</html>
"""

out = (HTML
       .replace("__TITLE__", title)
       .replace("__META__", f"{n_parts} 章 · {n_secs} 小節 · 面試備戰版")
       .replace("__PYG__", pyg_css)
       .replace("__CSS__", CSS)
       .replace("__TOC__", toc_html)
       .replace("__CONTENT__", content_html)
       .replace("__JS__", JS))

open(OUT, "w", encoding="utf-8").write(out)
print(f"wrote {OUT}  ({len(out):,} bytes)")
print(f"parts={n_parts} sections={n_secs} headings_in_toc={sum(1 for _ in toc_tokens)}")
