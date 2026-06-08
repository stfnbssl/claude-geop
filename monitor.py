"""Monitoraggio YouTube dei driver di attenzione (automazione end-to-end).

Pipeline (per ogni driver, o per i driver passati come argomento):
  1. costruisce la stringa di ricerca dai 'parole_chiave_associate' del driver
  2. esegue la ricerca su YouTube con yt-dlp (ambito: ultimo anno)
  3. estrae i metadati ESATTI dei video (data, views, durata, canale)
  4. applica il filtro (esclude i video > 1 mese E con < MIN_VIEWS views)
  5. salta i video gia' esaminati (registro persistente monitor_index.json)
  6. per i NUOVI video tenuti scarica il transcript (sottotitoli it/en via yt-dlp)
  7. aggiorna il registro e scrive monitor_results.json per l'analisi LLM (Cowork)

NB: il tagging semantico (matched_drivers ecc.) NON e' fatto qui: e' lavoro da LLM.

Uso:
    python monitor.py                 # tutti i driver
    python monitor.py D02 D07         # solo questi driver
    python monitor.py --n 40          # 40 risultati per ricerca (default 25)
    python monitor.py --no-transcripts
"""
import sys, os, re, json, glob, html, subprocess
from datetime import date, timedelta

for _stream in (sys.stdout, sys.stderr):  # console Windows cp1252 -> evita crash sui print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DRIVERS_FILE = r"C:\my\projects\geop\data\drivers_di_attenzione.json"
OUT_DIR = r"C:\my\projects\geop\data"
TRANSCRIPTS_DIR = os.path.join(OUT_DIR, "transcripts")
INDEX_FILE = os.path.join(OUT_DIR, "monitor_index.json")
RESULTS_FILE = os.path.join(OUT_DIR, "monitor_results.json")

SEARCH_N = 25          # risultati per ricerca/driver
MIN_VIEWS = 200        # soglia del filtro "poco visti"
YEAR_DAYS = 365        # ambito ricerca: ultimi 12 mesi
SUB_LANGS = "it.*,en.*"
ANCHOR = "geopolitica"
YTDLP = [sys.executable, "-m", "yt_dlp"]

TODAY = date.today()
YEAR_CUTOFF = TODAY - timedelta(days=YEAR_DAYS)


def minus_one_month(d):
    import calendar
    month = d.month - 1 or 12
    year = d.year - (1 if d.month == 1 else 0)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


MONTH_CUTOFF = minus_one_month(TODAY)


# ----------------------------------------------------------------- driver/query
def load_drivers():
    with open(DRIVERS_FILE, encoding="utf-8") as f:
        return json.load(f)["driver_di_attenzione"]


def build_query(driver):
    kws = driver.get("parole_chiave_associate", [])
    or_group = "(" + " OR ".join(f'"{k}"' for k in kws) + ")"
    return f'"{ANCHOR}" AND {or_group}'


# ----------------------------------------------------------------- yt-dlp calls
def run_ytdlp(args, timeout=300):
    """Esegue yt-dlp; ritorna (stdout, stderr, returncode)."""
    try:
        p = subprocess.run(YTDLP + args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1


def _warn_if_error(stderr, context):
    """Segnala il primo errore yt-dlp (es. SSL) invece di lasciarlo silenzioso."""
    for line in (stderr or "").splitlines():
        if "ERROR" in line:
            print(f"  [yt-dlp:{context}] {line.strip()[:160]}", file=sys.stderr)
            return


def search_flat(query, n):
    """Ricerca veloce (flat): ritorna lista di id video nell'ordine di rilevanza."""
    out, err, _ = run_ytdlp([f"ytsearch{n}:{query}", "--flat-playlist", "-J",
                            "--no-warnings", "--ignore-errors"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        _warn_if_error(err, "search")
        return []
    return [e["id"] for e in (data.get("entries") or []) if e and e.get("id")]


def extract_metadata(video_ids):
    """Estrazione completa: id -> metadati esatti (data, views, durata, canale)."""
    if not video_ids:
        return {}
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]
    out, err, _ = run_ytdlp(["--dump-json", "--no-warnings", "--ignore-errors",
                            "--skip-download"] + urls, timeout=600)
    if not out.strip():
        _warn_if_error(err, "metadata")
    meta = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        ud = j.get("upload_date")  # 'YYYYMMDD'
        published = f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud and len(ud) == 8 else None
        meta[j["id"]] = {
            "title": j.get("title"),
            "video_id": j["id"],
            "url": f"https://www.youtube.com/watch?v={j['id']}",
            "duration_seconds": j.get("duration"),
            "views_count": j.get("view_count"),
            "published": published,
            "channel": j.get("channel") or j.get("uploader"),
            "channel_url": j.get("channel_url") or j.get("uploader_url"),
            "description": (j.get("description") or "")[:500] or None,
        }
    return meta


# ----------------------------------------------------------------- transcripts
def vtt_to_text(path):
    """Estrae il testo pulito da un file .vtt (rimuove timestamp, tag, ripetizioni)."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "-->" in line or line.startswith("WEBVTT"):
                continue
            if line.startswith(("Kind:", "Language:", "NOTE")) or re.fullmatch(r"\d+", line):
                continue
            line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            if not line or (out and out[-1] == line):
                continue
            out.append(line)
    return " ".join(out)


def fetch_transcript(video_id):
    """Scarica i sottotitoli (it/en) e ritorna (status, lang, rel_path)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    run_ytdlp(["--skip-download", "--write-subs", "--write-auto-subs",
              "--sub-langs", SUB_LANGS, "--sub-format", "vtt",
              "-o", os.path.join(TRANSCRIPTS_DIR, "%(id)s.%(ext)s"),
              "--no-warnings", "--ignore-errors", url], timeout=120)
    vtts = glob.glob(os.path.join(TRANSCRIPTS_DIR, f"{video_id}*.vtt"))
    if not vtts:
        return "none", None, None
    # preferenza lingua: it > en > prima disponibile
    def lang_of(p):
        m = re.search(rf"{re.escape(video_id)}\.([\w-]+)\.vtt$", os.path.basename(p))
        return m.group(1) if m else "?"
    vtts.sort(key=lambda p: (not lang_of(p).startswith("it"),
                             not lang_of(p).startswith("en")))
    chosen = vtts[0]
    lang = lang_of(chosen)
    text = vtt_to_text(chosen)
    txt_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.{lang}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    # pulizia dei .vtt grezzi
    for p in vtts:
        try:
            os.remove(p)
        except OSError:
            pass
    return ("ok" if text else "empty"), lang, os.path.relpath(txt_path, OUT_DIR)


# ----------------------------------------------------------------- registry
def load_index():
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_on": None, "videos": {}}


def save_index(index):
    index["updated_on"] = TODAY.isoformat()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------- filtro
def passes_filter(meta):
    """Tieni il video salvo che sia (piu' vecchio di 1 mese) E (con < MIN_VIEWS views)."""
    pub = meta.get("published")
    if pub is None:
        return True  # senza data non posso escluderlo: lo tengo
    if pub < YEAR_CUTOFF.isoformat():
        return False  # fuori dall'ambito 'ultimo anno'
    views = meta.get("views_count")
    old = pub < MONTH_CUTOFF.isoformat()
    low = views is not None and views < MIN_VIEWS
    return not (old and low)


# ----------------------------------------------------------------- main
def main():
    argv = sys.argv[1:]
    search_n = SEARCH_N
    do_transcripts = True
    driver_filter = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--n":
            search_n = int(argv[i + 1]); i += 2
        elif a == "--no-transcripts":
            do_transcripts = False; i += 1
        else:
            driver_filter.append(a.upper()); i += 1

    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    drivers = load_drivers()
    if driver_filter:
        drivers = [d for d in drivers if d["id"] in driver_filter]
    index = load_index()
    print(f"Oggi: {TODAY} | ambito: dal {YEAR_CUTOFF} | cutoff 'vecchi': {MONTH_CUTOFF}")
    print(f"Driver da monitorare: {[d['id'] for d in drivers]}")

    # 1-2. ricerca per driver -> provenienza id -> driver
    found_via = {}  # video_id -> set(driver_id)
    for d in drivers:
        ids = search_flat(build_query(d), search_n)
        print(f"  {d['id']}: {len(ids)} risultati")
        for vid in ids:
            found_via.setdefault(vid, set()).add(d["id"])

    candidates = list(found_via)
    # 3. metadati: riusa quelli in index, estrai solo i nuovi
    new_ids = [v for v in candidates if v not in index["videos"]]
    print(f"Candidati: {len(candidates)} ({len(new_ids)} nuovi da estrarre)")
    fresh_meta = extract_metadata(new_ids)
    meta_map = {v: index["videos"][v] for v in candidates if v in index["videos"]}
    meta_map.update(fresh_meta)

    # 4-6. filtro, dedup, transcript dei nuovi tenuti
    kept_results = []
    n_new_kept = n_transcripts = 0
    for vid in candidates:
        meta = meta_map.get(vid)
        if not meta or not passes_filter(meta):
            continue
        already = vid in index["videos"]
        entry = dict(meta)
        entry["found_via_query"] = sorted(
            set(index.get("videos", {}).get(vid, {}).get("found_via_query", [])) | found_via[vid])
        entry["new"] = not already

        if not already:
            n_new_kept += 1
            status, lang, rel = ("skipped", None, None)
            if do_transcripts:
                status, lang, rel = fetch_transcript(vid)
                if status == "ok":
                    n_transcripts += 1
            entry.update(transcript_status=status, transcript_lang=lang,
                         transcript_file=rel, examined_on=TODAY.isoformat())
            index["videos"][vid] = {k: entry[k] for k in entry if k != "new"}
        else:
            prev = index["videos"][vid]
            prev["found_via_query"] = entry["found_via_query"]
            entry.update(transcript_status=prev.get("transcript_status"),
                         transcript_lang=prev.get("transcript_lang"),
                         transcript_file=prev.get("transcript_file"),
                         examined_on=prev.get("examined_on"))
        kept_results.append(entry)

    save_index(index)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generato_il": TODAY.isoformat(),
            "ambito_temporale": f"ultimi {YEAR_DAYS} giorni (dal {YEAR_CUTOFF})",
            "filtro": f"esclusi video pubblicati prima del {MONTH_CUTOFF} E con views < {MIN_VIEWS}",
            "totale_tenuti": len(kept_results),
            "nuovi": n_new_kept,
            "videos": kept_results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nTenuti: {len(kept_results)} | nuovi: {n_new_kept} | "
          f"transcript scaricati: {n_transcripts}")
    print(f"-> {RESULTS_FILE}")
    print(f"-> {INDEX_FILE}  (registro: {len(index['videos'])} video totali)")


if __name__ == "__main__":
    main()
