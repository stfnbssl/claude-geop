"""Estrae video + metadati dalle pagine di risultati YouTube salvate in Markdown.

Processa automaticamente tutti i file 'youtube *.md' nella cartella geop,
producendo un JSON per ciascuno in geop\\data\\, piu' un 'youtube geop - all.json'
combinato e deduplicato per video_id.

Collegamento ai driver di attenzione (drivers_di_attenzione.json):
  - se il nome file contiene un id driver (es. 'youtube driver D10.md'), il
    risultato e ogni video vengono taggati con quel driver di provenienza;
  - per OGNI video viene calcolato 'matched_drivers': i driver le cui parole
    chiave compaiono nel titolo o nella descrizione (tagging automatico).

Convenzione di naming consigliata per le pagine salvate dal browser:
  - generiche:   'youtube geop - 1.md', 'youtube geop - 2.md', ...
  - per driver:  'youtube driver D01.md' ... 'youtube driver D12.md'

Uso:
    python parse_youtube.py                 # tutti i file
    python parse_youtube.py "...path.md"    # uno o piu' file specifici
"""
import re, json, sys, glob, os
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs, unquote

GEOP_DIR = r"C:\my\obsidian\Stefano\geop"
DATA_DIR = os.path.join(GEOP_DIR, "data")
PATTERN = os.path.join(GEOP_DIR, "youtube *.md")
DRIVERS_FILE = r"C:\my\projects\geop\data\drivers_di_attenzione.json"

# Data di riferimento = giorno in cui i risultati sono stati salvati (frontmatter "created").
REF_DATE = date(2026, 6, 2)
EXTRACTED_ON = REF_DATE.isoformat()

# Filtro: escludi video pubblicati da piu' di 1 mese (di calendario) E con meno
# di MIN_VIEWS visualizzazioni. Cutoff = REF_DATE meno un mese.
MIN_VIEWS = 200


def minus_one_month(d):
    """Sottrae un mese di calendario, gestendo i giorni a fine mese."""
    month = d.month - 1 or 12
    year = d.year - (1 if d.month == 1 else 0)
    # clamp del giorno al massimo valido per il mese di destinazione
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


CUTOFF_DATE = minus_one_month(REF_DATE)  # video con stima < cutoff = "vecchi"

# Giorni approssimati per unita' temporale italiana (singolare/plurale).
UNIT_DAYS = {
    "second": 1 / 86400, "minut": 1 / 1440, "or": 1 / 24,
    "giorn": 1, "settiman": 7, "mes": 30, "ann": 365,
}


def views_to_int(views):
    """'79K' -> 79000, '4,2K' -> 4200, '84' -> 84, None -> None."""
    if not views:
        return None
    s = views.strip().upper().replace(".", "").replace(",", ".")
    mult = 1
    if s.endswith("K"):
        mult, s = 1000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(round(float(s) * mult))
    except ValueError:
        return None


def relative_to_days(rel):
    """'4 mesi fa' -> 120, '2 settimane fa' -> 14, gestisce il prefisso streaming."""
    if not rel:
        return None
    m = re.search(r'(\d+)\s+([a-zàèéìòù]+)\s+fa', rel.strip(), re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    word = m.group(2).lower()
    for stem, days in UNIT_DAYS.items():
        if word.startswith(stem):
            return n * days
    return None

heading_re = re.compile(r'^###\s+\[(.*?)\]\((https://www\.youtube\.com/watch\?v=[^)]*?)(?:\s+"[^"]*")?\)\s*$')
watch_url_re = re.compile(r'https://www\.youtube\.com/watch\?v=([\w-]+)')
dur_re = re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?$')
views_re = re.compile(r'visualizzazion')
chan_re = re.compile(r'^\[([^\]]+)\]\((https://www\.youtube\.com/@[^)]+)\)\s*$')
MARKERS = ("Nuovo", "Sponsorizzato", "Ora in riproduzione", "Anteprima",
           "Riproduci tutto", "Guarda piu' tardi", "Guarda più tardi",
           "Aggiungi alla coda")


def extract_query(lines):
    """Recupera e decodifica la query di ricerca dal frontmatter 'source:'."""
    for line in lines[:30]:
        if line.startswith("source:"):
            url = line.split("source:", 1)[1].strip().strip('"')
            qs = parse_qs(urlparse(url).query)
            if "search_query" in qs:
                return unquote(qs["search_query"][0])
    return None


def load_drivers():
    """Carica i driver: lista di (id, nome, [pattern parola-intera per keyword]).

    Il match a parola intera evita falsi positivi (es. la keyword 'IA' che
    altrimenti combacerebbe dentro 'ItalIA', 'RussIA', ...).
    """
    if not os.path.exists(DRIVERS_FILE):
        return []
    with open(DRIVERS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for d in data.get("driver_di_attenzione", []):
        pats = [re.compile(r'\b' + re.escape(k) + r'\b', re.IGNORECASE)
                for k in d.get("parole_chiave_associate", [])]
        out.append((d["id"], d["nome"], pats))
    return out


def driver_id_from_path(path):
    """Estrae un id driver (es. 'D10') dal nome file, se presente."""
    m = re.search(r'\b(D\d{1,2})\b', os.path.basename(path))
    return m.group(1) if m else None


def match_drivers(title, description, drivers):
    """Driver le cui parole chiave (parola intera) compaiono in titolo/descrizione."""
    text = f"{title or ''} {description or ''}"
    return [did for did, _nome, pats in drivers if any(p.search(text) for p in pats)]


def parse_file(path, drivers=None):
    drivers = drivers or []
    source_driver_id = driver_id_from_path(path)
    source_driver = None
    if source_driver_id:
        nome = next((n for d, n, _ in drivers if d == source_driver_id), None)
        source_driver = {"id": source_driver_id, "nome": nome}

    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    videos = []
    seen = set()

    for i, line in enumerate(lines):
        m = heading_re.match(line.strip())
        if not m:
            continue
        title = m.group(1).strip()
        vid_m = watch_url_re.search(m.group(2))
        if not vid_m:
            continue
        vid = vid_m.group(1)
        if vid in seen:
            continue
        seen.add(vid)

        # durata: cerca all'indietro una riga con solo un tempo
        duration = None
        for j in range(i - 1, max(i - 16, -1), -1):
            s = lines[j].strip()
            if dur_re.match(s):
                duration = s
                break
            if s.startswith("###"):
                break

        # finestra in avanti fino al prossimo heading
        views = published_relative = channel = channel_url = description = None
        plain_lines = []

        for j in range(i + 1, min(i + 14, len(lines))):
            s = lines[j].strip()
            if not s:
                continue
            if s.startswith("###"):
                break
            if views is None and views_re.search(s):
                vm = re.match(r'^(.+?)\s+visualizzazion[a-z]*(.*)$', s)
                if vm:
                    views = vm.group(1).strip()
                    published_relative = vm.group(2).strip() or None
                continue
            cm = chan_re.match(s)
            if cm and channel is None and not s.startswith("[!["):
                channel = cm.group(1).strip()
                channel_url = cm.group(2).strip()
                continue
            if not s.startswith("[") and not s.startswith("!") and not dur_re.match(s) \
               and s not in MARKERS and not s.endswith("capitoli"):
                plain_lines.append(s)
                if channel is not None and description is None:
                    description = s
                    break

        # fallback: collaborazioni con canale come testo (senza link)
        if channel is None and plain_lines:
            channel = plain_lines[0]
            if description is None and len(plain_lines) > 1:
                description = plain_lines[1]
        if description is None and channel is not None and plain_lines:
            for s in plain_lines:
                if s != channel:
                    description = s
                    break

        views_count = views_to_int(views)
        age_days = relative_to_days(published_relative)
        if age_days is not None:
            published_estimate = (REF_DATE - timedelta(days=age_days)).isoformat()
        else:
            published_estimate = None

        videos.append({
            "title": title,
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "duration": duration,
            "views": views,
            "views_count": views_count,
            "published_relative": published_relative,
            "published_estimate": published_estimate,
            "channel": channel,
            "channel_url": channel_url,
            "description": description,
            "source_driver_id": source_driver_id,
            "matched_drivers": match_drivers(title, description, drivers),
        })

    # Filtro: escludi i video pubblicati da > 1 mese E poco visti (< MIN_VIEWS).
    kept, excluded_count = [], 0
    for v in videos:
        old = v["published_estimate"] is not None and v["published_estimate"] < CUTOFF_DATE.isoformat()
        low = v["views_count"] is not None and v["views_count"] < MIN_VIEWS
        if old and low:
            excluded_count += 1
        else:
            kept.append(v)

    return {
        "source_file": path,
        "source_driver": source_driver,
        "source_query": extract_query(lines),
        "extracted_on": EXTRACTED_ON,
        "filter": f"esclusi video pubblicati prima del {CUTOFF_DATE.isoformat()} E con views < {MIN_VIEWS}",
        "count": len(kept),
        "excluded_count": excluded_count,
        "videos": kept,
    }


def main():
    files = sys.argv[1:] or sorted(glob.glob(PATTERN))
    if not files:
        print(f"Nessun file trovato con il pattern: {PATTERN}")
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    drivers = load_drivers()
    if drivers:
        print(f"Driver caricati: {len(drivers)}")

    combined = {}  # video_id -> video arricchito (dedup tra file)
    sources = []

    for path in files:
        result = parse_file(path, drivers)
        base = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(DATA_DIR, base + ".json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        drv = f" [driver {result['source_driver']['id']}]" if result["source_driver"] else ""
        print(f"{base}{drv}: {result['count']} video tenuti, "
              f"{result['excluded_count']} esclusi (vecchi+poco visti) -> {out}")
        sources.append({"file": path, "driver": result["source_driver"],
                        "query": result["source_query"], "count": result["count"]})
        for v in result["videos"]:
            vid = v["video_id"]
            if vid not in combined:
                c = dict(v)
                c["found_in_files"] = []
                c["found_via_drivers"] = set(v.get("matched_drivers") or [])
                combined[vid] = c
            c = combined[vid]
            if base not in c["found_in_files"]:
                c["found_in_files"].append(base)
            c["found_via_drivers"].update(v.get("matched_drivers") or [])
            if v.get("source_driver_id"):
                c["found_via_drivers"].add(v["source_driver_id"])

    # normalizza i set in liste ordinate
    for c in combined.values():
        c["found_via_drivers"] = sorted(c.pop("found_via_drivers"))

    if len(files) > 1:
        all_out = os.path.join(DATA_DIR, "youtube geop - all.json")
        with open(all_out, "w", encoding="utf-8") as f:
            json.dump({
                "sources": sources,
                "extracted_on": EXTRACTED_ON,
                "count": len(combined),
                "videos": list(combined.values()),
            }, f, ensure_ascii=False, indent=2)
        print(f"\nCombinato (dedup): {len(combined)} video unici -> {all_out}")


if __name__ == "__main__":
    main()
