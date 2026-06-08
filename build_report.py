r"""Genera un report HTML autoconsistente (dati embeddati) dai risultati del monitoraggio.

Legge:  data\drivers_di_attenzione.json, data\monitor_index.json, data\cowork_analysis.json
Scrive: data\report.html   (apribile col doppio click, nessun server necessario)

Uso:
    python build_report.py
"""
import json, os, sys
from datetime import date

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OUT_DIR = r"C:\my\projects\geop\data"
DRIVERS_FILE = os.path.join(OUT_DIR, "drivers_di_attenzione.json")
INDEX_FILE = os.path.join(OUT_DIR, "monitor_index.json")
ANALYSIS_FILE = os.path.join(OUT_DIR, "cowork_analysis.json")
REPORT_FILE = os.path.join(OUT_DIR, "report.html")


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def build_data():
    drivers_raw = load(DRIVERS_FILE, {}).get("driver_di_attenzione", [])
    drivers = {d["id"]: {"nome": d["nome"], "categoria": d.get("categoria", "")}
               for d in drivers_raw}
    index = load(INDEX_FILE, {"videos": {}})["videos"]
    analyses = load(ANALYSIS_FILE, [])

    collected = []
    for v in index.values():
        collected.append({
            "video_id": v.get("video_id"),
            "title": v.get("title"),
            "url": v.get("url"),
            "views_count": v.get("views_count"),
            "published": v.get("published"),
            "channel": v.get("channel"),
            "found_via_query": v.get("found_via_query", []),
            "transcript_status": v.get("transcript_status"),
            "transcript_file": (v.get("transcript_file") or "").replace("\\", "/"),
            "analyzed_on": v.get("analyzed_on"),
        })
    return {
        "generated_on": date.today().isoformat(),
        "drivers": drivers,
        "analyses": analyses,
        "collected": collected,
        "stats": {"collected": len(collected), "analyzed": len(analyses)},
    }


HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Geopolitica — Driver di attenzione · Report</title>
<style>
  :root{
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a;
    --txt:#e6e8ec; --muted:#9aa3b2; --accent:#6ea8fe;
    --red:#e5534b; --orange:#d98c30; --gray:#6b7280; --green:#3fb950;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
    font:15px/1.5 system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  header{padding:24px 28px;border-bottom:1px solid var(--line);
    background:linear-gradient(180deg,#161a22,#0f1115)}
  h1{margin:0 0 4px;font-size:20px}
  .sub{color:var(--muted);font-size:13px}
  .wrap{max-width:1200px;margin:0 auto;padding:24px 28px}
  .stats{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:14px 18px;min-width:130px}
  .stat .n{font-size:26px;font-weight:700}
  .stat .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
  h2{font-size:15px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
    border-bottom:1px solid var(--line);padding-bottom:8px;margin:28px 0 16px}
  .drivers{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
  .dcard{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .dcard .id{font-weight:700;font-size:13px}
  .dcard .nm{font-size:12.5px;color:var(--muted);margin:2px 0 10px;min-height:34px}
  .dmeta{display:flex;justify-content:space-between;align-items:center;font-size:12px}
  .trend{font-weight:700;padding:2px 8px;border-radius:20px;color:#fff}
  .bar{height:6px;border-radius:4px;background:var(--panel2);margin-top:8px;overflow:hidden}
  .bar > i{display:block;height:100%}
  .controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
  input,select{background:var(--panel2);border:1px solid var(--line);color:var(--txt);
    border-radius:8px;padding:8px 10px;font-size:13px}
  input{min-width:240px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:14px 16px;margin-bottom:10px}
  .card h3{margin:0 0 4px;font-size:15.5px}
  .card h3 a{color:var(--txt);text-decoration:none}
  .card h3 a:hover{color:var(--accent)}
  .meta{color:var(--muted);font-size:12.5px;margin-bottom:8px;display:flex;gap:12px;flex-wrap:wrap}
  .chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
  .chip{font-size:11.5px;padding:3px 8px;border-radius:20px;border:1px solid var(--line);
    background:var(--panel2);cursor:default}
  .chip b{font-weight:700}
  details{margin-top:6px}
  summary{cursor:pointer;color:var(--accent);font-size:13px}
  .detail{margin-top:10px;font-size:13.5px}
  .detail .blk{margin:8px 0}
  .detail .lbl{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
  .ev{border-left:2px solid var(--line);padding-left:10px;color:#cdd3dd;margin:4px 0;font-style:italic}
  ul{margin:4px 0;padding-left:18px}
  .pill{font-size:11px;padding:2px 7px;border-radius:6px;background:var(--panel2);border:1px solid var(--line)}
  .backlog .row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;
    border-bottom:1px solid var(--line);font-size:13px}
  .backlog a{color:var(--txt);text-decoration:none}.backlog a:hover{color:var(--accent)}
  .hidden{display:none}
  .foot{color:var(--muted);font-size:12px;margin-top:30px;text-align:center}
</style>
</head>
<body>
<header>
  <h1>Geopolitica — Driver di attenzione</h1>
  <div class="sub" id="subtitle"></div>
</header>
<div class="wrap">
  <div class="stats" id="stats"></div>

  <h2>Cruscotto driver (sui video analizzati)</h2>
  <div class="drivers" id="drivers"></div>

  <h2>Video analizzati</h2>
  <div class="controls">
    <input id="q" placeholder="Cerca per titolo, canale, testo…">
    <select id="fdriver"><option value="">Tutti i driver</option></select>
    <select id="sort">
      <option value="views">Ordina: views ↓</option>
      <option value="date">Ordina: data ↓</option>
      <option value="ndrv">Ordina: n. driver ↓</option>
    </select>
    <span class="pill" id="acount"></span>
  </div>
  <div id="analyses"></div>

  <h2>Backlog (raccolti, non ancora analizzati)</h2>
  <div class="backlog" id="backlog"></div>

  <div class="foot" id="foot"></div>
</div>

<script>
const DATA = __DATA__;
const DRV = DATA.drivers;
const trendColor = t => t<=-2?'var(--red)':t<0?'var(--orange)':t===0?'var(--gray)':'var(--green)';
const fmt = n => (n==null?'—':n.toLocaleString('it-IT'));
const drvName = id => DRV[id] ? DRV[id].nome : id;

// indice meta per video_id (per transcript / views nel dettaglio)
const META = {};
DATA.collected.forEach(c => META[c.video_id]=c);

// ---- stats
document.getElementById('subtitle').textContent =
  `Generato il ${DATA.generated_on} · ${DATA.stats.collected} video raccolti · ${DATA.stats.analyzed} analizzati`;
const statsEl = document.getElementById('stats');
[['Raccolti',DATA.stats.collected],['Analizzati',DATA.stats.analyzed],
 ['Driver',Object.keys(DRV).length],
 ['Da analizzare',DATA.stats.collected-DATA.stats.analyzed]]
 .forEach(([l,n])=>{statsEl.insertAdjacentHTML('beforeend',
   `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`);});

// ---- driver dashboard
const freq={}, trendSum={}, trendN={};
DATA.analyses.forEach(a=>(a.matched_drivers||[]).forEach(m=>{
  freq[m.driver_id]=(freq[m.driver_id]||0)+1;
  trendSum[m.driver_id]=(trendSum[m.driver_id]||0)+(m.valutazione_trend||0);
  trendN[m.driver_id]=(trendN[m.driver_id]||0)+1;
}));
const maxFreq=Math.max(1,...Object.values(freq));
const dEl=document.getElementById('drivers');
Object.keys(DRV).sort().forEach(id=>{
  const f=freq[id]||0, avg=trendN[id]?trendSum[id]/trendN[id]:null;
  dEl.insertAdjacentHTML('beforeend',`
   <div class="dcard">
     <div class="id">${id}</div>
     <div class="nm">${DRV[id].nome}</div>
     <div class="dmeta">
       <span>${f} video</span>
       ${avg==null?'<span style="color:var(--muted)">n/d</span>':
         `<span class="trend" style="background:${trendColor(avg)}">trend ${avg>0?'+':''}${avg.toFixed(1)}</span>`}
     </div>
     <div class="bar"><i style="width:${Math.round(f/maxFreq*100)}%;background:var(--accent)"></i></div>
   </div>`);
});
// popola filtro driver
const fd=document.getElementById('fdriver');
Object.keys(DRV).sort().forEach(id=>fd.insertAdjacentHTML('beforeend',
  `<option value="${id}">${id} — ${DRV[id].nome}</option>`));

// ---- analyses
function chip(m){
  return `<span class="chip" title="${drvName(m.driver_id)}">${m.driver_id}
    · <b>r${m.rilevanza}</b>
    · <span style="color:${trendColor(m.valutazione_trend)}">t${m.valutazione_trend>0?'+':''}${m.valutazione_trend}</span></span>`;
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function card(a){
  const meta=META[a.video_id]||{};
  const views=meta.views_count;
  const mds=(a.matched_drivers||[]).slice().sort((x,y)=>y.rilevanza-x.rilevanza);
  const tf=meta.transcript_file;
  const drvDetail=mds.map(m=>`
    <div class="blk">
      <div><b>${m.driver_id}</b> — ${drvName(m.driver_id)} · rilevanza ${m.rilevanza} ·
        <span style="color:${trendColor(m.valutazione_trend)}">trend ${m.valutazione_trend>0?'+':''}${m.valutazione_trend}</span></div>
      ${(m.manifestazioni_rilevate||[]).length?`<ul>${m.manifestazioni_rilevate.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      ${m.evidenza?`<div class="ev">${esc(m.evidenza)}</div>`:''}
    </div>`).join('');
  return `<div class="card" data-drv="${mds.map(m=>m.driver_id).join(',')}"
       data-text="${esc((a.title||'')+' '+(a.channel||'')+' '+(a.sintesi||'')).toLowerCase()}"
       data-views="${views||0}" data-date="${a.published||''}" data-ndrv="${mds.length}">
    <h3><a href="${a.url}" target="_blank">${esc(a.title)}</a></h3>
    <div class="meta">
      <span>${esc(a.channel||'')}</span>
      <span>👁 ${fmt(views)}</span>
      <span>📅 ${a.published||'—'}</span>
      <span>conf: ${a.analysis_confidence||'—'}</span>
      ${tf?`<a href="${tf}" target="_blank" style="color:var(--accent)">transcript</a>`:''}
    </div>
    <div class="chips">${mds.map(chip).join('')}</div>
    <details><summary>Dettaglio analisi</summary>
      <div class="detail">
        <div class="blk"><div class="lbl">Sintesi</div>${esc(a.sintesi)}</div>
        <div class="blk"><div class="lbl">Driver rilevati</div>${drvDetail}</div>
        ${(a.citazioni_notevoli||[]).length?`<div class="blk"><div class="lbl">Citazioni</div><ul>${a.citazioni_notevoli.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
        ${(a.temi_emergenti||[]).length?`<div class="blk"><div class="lbl">Temi emergenti</div><ul>${a.temi_emergenti.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
        ${a.note?`<div class="blk"><div class="lbl">Note</div>${esc(a.note)}</div>`:''}
      </div>
    </details>
  </div>`;
}
const aEl=document.getElementById('analyses');
function render(){
  const q=document.getElementById('q').value.toLowerCase().trim();
  const fdrv=document.getElementById('fdriver').value;
  const sort=document.getElementById('sort').value;
  let items=DATA.analyses.slice();
  items.sort((a,b)=>{
    if(sort==='date') return (b.published||'').localeCompare(a.published||'');
    if(sort==='ndrv') return (b.matched_drivers||[]).length-(a.matched_drivers||[]).length;
    return ((META[b.video_id]||{}).views_count||0)-((META[a.video_id]||{}).views_count||0);
  });
  let shown=0;
  aEl.innerHTML=items.map(a=>{
    const txt=((a.title||'')+' '+(a.channel||'')+' '+(a.sintesi||'')).toLowerCase();
    const drvs=(a.matched_drivers||[]).map(m=>m.driver_id);
    if(q && !txt.includes(q)) return '';
    if(fdrv && !drvs.includes(fdrv)) return '';
    shown++; return card(a);
  }).join('');
  document.getElementById('acount').textContent=`${shown} mostrati`;
}
['q','fdriver','sort'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();

// ---- backlog
const bl=DATA.collected.filter(c=>!c.analyzed_on)
  .sort((a,b)=>(b.views_count||0)-(a.views_count||0));
document.getElementById('backlog').innerHTML = bl.map(c=>`
  <div class="row">
    <a href="${c.url}" target="_blank">${esc(c.title)}</a>
    <span style="color:var(--muted);white-space:nowrap">${fmt(c.views_count)} · ${c.published||'—'} · [${(c.found_via_query||[]).join(',')}]</span>
  </div>`).join('') || '<div style="color:var(--muted)">Nessun video in attesa.</div>';

document.getElementById('foot').textContent =
  'Report statico generato da build_report.py — i dati sono embeddati nel file.';
</script>
</body>
</html>
"""


def main():
    data = build_data()
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report generato: {REPORT_FILE}")
    print(f"  {data['stats']['collected']} raccolti · {data['stats']['analyzed']} analizzati")


if __name__ == "__main__":
    main()
