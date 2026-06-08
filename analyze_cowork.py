"""Chiamante che fa analizzare a Cowork (claude -p headless) i video raccolti.

Per ogni esecuzione:
  1. (ri)genera cowork\\CLAUDE.md dai driver (istruzioni + schema sempre in sync)
  2. seleziona i N video piu' visti NON ancora analizzati (default 10)
  3. per ciascuno invoca 'claude -p' nella cartella cowork passando UN solo transcript
  4. al risultato: marca il video come analizzato (monitor_index.json) e accumula
     l'analisi in cowork_analysis.json

Uso:
    python analyze_cowork.py                # top 10 non analizzati
    python analyze_cowork.py --limit 1      # utile per test
    python analyze_cowork.py --model sonnet # cambia modello (default: quello di sessione)
"""
import sys, os, re, json, subprocess
from datetime import date

# La console Windows (cp1252) non rappresenta alcuni caratteri dei titoli
# (es. accenti combinanti U+0301): forziamo UTF-8 per non far crashare i print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT_DIR = r"C:\my\projects\geop"
OUT_DIR = os.path.join(PROJECT_DIR, "data")
DRIVERS_FILE = os.path.join(OUT_DIR, "drivers_di_attenzione.json")
INDEX_FILE = os.path.join(OUT_DIR, "monitor_index.json")
ANALYSIS_FILE = os.path.join(OUT_DIR, "cowork_analysis.json")
COWORK_DIR = os.path.join(PROJECT_DIR, "cowork")
CLAUDE_MD = os.path.join(COWORK_DIR, "CLAUDE.md")

DEFAULT_LIMIT = 10
TODAY = date.today().isoformat()


# ----------------------------------------------------------- genera CLAUDE.md
def build_claude_md(drivers):
    rows = []
    for d in drivers:
        man = "; ".join(d.get("manifestazioni_osservabili", []))
        rows.append(f"- **{d['id']} — {d['nome']}** _({d.get('categoria','')})_\n"
                    f"  - manifestazioni osservabili: {man}")
    drv_block = "\n".join(rows)
    md = f"""# Istruzioni Cowork — Analisi di UN singolo video geopolitico

Sei un analista geopolitico. Ricevi nel messaggio utente i **metadati** e il
**transcript** di UN solo video YouTube. Analizzalo rispetto ai 12 driver di
attenzione qui sotto e restituisci **esclusivamente** un oggetto JSON conforme
allo schema indicato — nessun testo prima o dopo, nessun code fence.

## I 12 driver di attenzione
{drv_block}

## Cosa fare
1. Determina quali driver sono **effettivamente trattati** nel video (analisi
   semantica del transcript, non semplice presenza di parole chiave).
2. Per ogni driver con rilevanza >= 1, compila un elemento di `matched_drivers`
   **citando il transcript** in `evidenza`.
3. Riporta i temi rilevanti fuori dai 12 driver in `temi_emergenti`.

## Regole
- Ancorati alle prove: nessun driver senza `evidenza` testuale dal transcript.
- Niente deduzioni non espresse; se ambiguo, abbassa `rilevanza` e annota in `note`.
- `rilevanza`: 0 assente · 1 citato di sfuggita · 2 tema secondario · 3 tema centrale
  (includi solo driver con rilevanza >= 1).
- `valutazione_trend`: da -3 (il driver accelera verso la crisi) a +3 (si attenua),
  0 = neutro/descrittivo.
- `manifestazioni_rilevate`: scegli SOLO dalla lista del driver; manifestazioni nuove vanno in `note`.
- Se il transcript e' assente (te lo segnalo nei metadati), analizza da titolo/descrizione
  e imposta `analysis_confidence` = "low".

## Schema di output (un solo oggetto JSON)
{{
  "video_id": "string",
  "title": "string",
  "url": "string",
  "published": "YYYY-MM-DD",
  "channel": "string",
  "analysis_confidence": "high | medium | low",
  "sintesi": "2-3 frasi",
  "matched_drivers": [
    {{
      "driver_id": "Dxx",
      "rilevanza": 0,
      "valutazione_trend": 0,
      "manifestazioni_rilevate": ["..."],
      "evidenza": "citazione/parafrasi puntuale dal transcript",
      "contesto": "facoltativo"
    }}
  ],
  "entita_chiave": {{ "persone": [], "luoghi": [], "organizzazioni": [] }},
  "citazioni_notevoli": ["..."],
  "temi_emergenti": ["..."],
  "note": "string"
}}
"""
    os.makedirs(COWORK_DIR, exist_ok=True)
    with open(CLAUDE_MD, "w", encoding="utf-8") as f:
        f.write(md)


# ----------------------------------------------------------- I/O registro
def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------- prompt + chiamata
def build_prompt(meta):
    tf = meta.get("transcript_file")
    transcript = None
    if tf:
        p = os.path.join(OUT_DIR, tf)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                transcript = f.read()
    has_t = transcript is not None and meta.get("transcript_status") == "ok"
    lines = [
        "Analizza il seguente singolo video seguendo le istruzioni in CLAUDE.md.",
        "Restituisci SOLO l'oggetto JSON dell'analisi, senza testo aggiuntivo ne' code fence.",
        "",
        "<METADATA>",
        f"video_id: {meta.get('video_id')}",
        f"title: {meta.get('title')}",
        f"url: {meta.get('url')}",
        f"published: {meta.get('published')}",
        f"channel: {meta.get('channel')}",
        f"views_count: {meta.get('views_count')}",
        f"transcript_presente: {'si' if has_t else 'NO (analizza da titolo/descrizione)'}",
        "</METADATA>",
        "",
        f"<DESCRIPTION>\n{meta.get('description') or ''}\n</DESCRIPTION>",
    ]
    if has_t:
        lines += ["", f"<TRANSCRIPT lang={meta.get('transcript_lang')}>",
                  transcript, "</TRANSCRIPT>"]
    return "\n".join(lines)


def call_cowork(prompt, model=None, timeout=420):
    cmd = ["claude", "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    p = subprocess.run(cmd, cwd=COWORK_DIR, input=prompt, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    try:
        env = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None, f"envelope non parsabile (stderr: {p.stderr[:200]})"
    if env.get("is_error"):
        return None, f"claude is_error: {env.get('result')!r}"
    raw = (env.get("result") or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()  # togli eventuali fence
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, f"output non-JSON: {raw[:200]}"


# ----------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    limit, model = DEFAULT_LIMIT, None
    i = 0
    while i < len(argv):
        if argv[i] == "--limit":
            limit = int(argv[i + 1]); i += 2
        elif argv[i] == "--model":
            model = argv[i + 1]; i += 2
        else:
            i += 1

    drivers = load_json(DRIVERS_FILE, {}).get("driver_di_attenzione", [])
    build_claude_md(drivers)

    index = load_json(INDEX_FILE, {"videos": {}})
    analysis = load_json(ANALYSIS_FILE, [])
    done_ids = {a["video_id"] for a in analysis}

    pool = [v for v in index.get("videos", {}).values()
            if not v.get("analyzed_on") and v.get("video_id") not in done_ids]
    pool.sort(key=lambda v: v.get("views_count") or 0, reverse=True)
    selected = pool[:limit]
    print(f"Candidati non analizzati: {len(pool)} | seleziono i {len(selected)} piu' visti")

    ok = fail = 0
    for n, meta in enumerate(selected, 1):
        vid = meta["video_id"]
        print(f"[{n}/{len(selected)}] {vid}  {(meta.get('views_count') or 0):>9,}  "
              f"{(meta.get('title') or '')[:50]}")
        try:
            result, err = call_cowork(build_prompt(meta), model=model)
        except subprocess.TimeoutExpired:
            result, err = None, "timeout"
        if result is None:
            print(f"     SALTATO: {err}")
            fail += 1
            continue
        # marca analizzato + accumula (salvataggio incrementale)
        analysis.append(result)
        index["videos"][vid]["analyzed_on"] = TODAY
        save_json(ANALYSIS_FILE, analysis)
        save_json(INDEX_FILE, index)
        nd = len(result.get("matched_drivers", []))
        print(f"     OK: {nd} driver rilevati, conf={result.get('analysis_confidence')}")
        ok += 1

    print(f"\nAnalizzati: {ok} | falliti/saltati: {fail}")
    print(f"-> {ANALYSIS_FILE}  (totale analizzati: {len(analysis)})")
    print(f"-> CLAUDE.md rigenerato in {CLAUDE_MD}")


if __name__ == "__main__":
    main()
