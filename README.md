# Geop — Monitoraggio geopolitico dei "driver di attenzione"

Pipeline in Python che, partendo da una lista di **driver di attenzione** geopolitici,
cerca video YouTube pertinenti, ne estrae metadati e transcript, e li fa analizzare a
un agente LLM (Claude Code headless, "Cowork") producendo un'analisi strutturata e un
report HTML.

---

## Flusso generale

```
drivers_di_attenzione.json
        │
        ▼
  monitor.py ───► ricerca YouTube (yt-dlp, ultimo anno) ──► metadati esatti
        │           + filtro (età/views) + dedup (registro)
        │           + download transcript (sottotitoli it/en)
        ▼
  monitor_index.json   (registro persistente)  +  transcripts/*.txt
        │
        ▼
  analyze_cowork.py ──► per i N video più visti non analizzati:
        │                 claude -p (1 transcript per chiamata) ──► analisi JSON
        ▼
  cowork_analysis.json  (analisi accumulate)
        │
        ▼
  build_report.py ───► data/report.html  (visualizzazione)
```

Il **tagging semantico** dei driver (quali driver un video tratta davvero, con quale
intensità/trend) è fatto dall'LLM, **non** dal codice Python: il codice si occupa solo
di raccolta, filtri, dedup, orchestrazione e presentazione.

---

## Prerequisiti (setup una tantum)

- **Python 3.13** (già presente).
- **yt-dlp** e **pip-system-certs**:
  ```powershell
  python -m pip install yt-dlp pip-system-certs
  ```
  `pip-system-certs` è necessario su questa macchina: la rete fa ispezione TLS e senza
  di esso yt-dlp fallisce con `CERTIFICATE_VERIFY_FAILED` (usa lo store certificati di Windows).
- **Claude Code CLI** (`claude`) per le analisi — già installato (v2.1.x).

Nessun `ffmpeg` necessario (i sottotitoli sono scaricati in formato `.vtt`).

---

## File del progetto

| File | Ruolo |
|------|-------|
| `drivers_di_attenzione.json` *(in `data/`)* | **Input umano**: i 12 driver, ognuno con `parole_chiave_associate` e `manifestazioni_osservabili`. |
| `build_queries.py` | Genera stringhe di ricerca YouTube + URL (per ricerche manuali nel browser). Output in `data/drivers_youtube_queries.{json,md}`. |
| `monitor.py` | **Raccolta**: ricerca, metadati, filtro, dedup, transcript. |
| `analyze_cowork.py` | **Analisi**: invoca Claude headless su 1 transcript per volta. |
| `cowork/CLAUDE.md` | Istruzioni per l'agente di analisi (rigenerato dai driver a ogni run). |
| `build_report.py` | Genera il report HTML. |
| `parse_youtube.py` | *(legacy)* Parser delle pagine HTML salvate a mano — superato da `monitor.py`. |

### File dati prodotti (in `data/`)

| File | Contenuto |
|------|-----------|
| `monitor_index.json` | Registro di **tutti** i video raccolti (dedup tra run). Campi chiave: metadati esatti, `found_via_query`, `transcript_*`, `analyzed_on`. |
| `monitor_results.json` | Output dell'**ultima** run di raccolta (solo i video tenuti). |
| `transcripts/<id>.<lang>.txt` | Transcript ripuliti. |
| `cowork_analysis.json` | Array delle **analisi** LLM (si accumula tra run). |
| `report.html` | Report visuale (dati embeddati, apribile col doppio click). |

---

## Come si esegue

### 1. (Opzionale) Query manuali per il browser
```powershell
python build_queries.py
```
Apri `data/drivers_youtube_queries.md`: per ogni driver hai la query e un link YouTube
già filtrato sull'ultimo anno.

### 2. Nuova ricerca / raccolta
```powershell
python monitor.py                  # tutti i 12 driver
python monitor.py D02 D07          # solo alcuni driver
python monitor.py --n 40           # 40 risultati per ricerca (default 25)
python monitor.py --no-transcripts # salta il download dei transcript
```
- Ambito: **ultimi 365 giorni**.
- Filtro: esclude i video pubblicati da **più di 1 mese** **E** con **meno di 200 views**.
- I video già nel registro vengono saltati; per i nuovi tenuti scarica il transcript.

### 3. Nuova analisi (Cowork)
```powershell
python analyze_cowork.py                 # i 10 più visti non ancora analizzati
python analyze_cowork.py --limit 20      # quanti analizzarne
python analyze_cowork.py --model sonnet  # modello (default: quello di sessione, es. Opus)
```
- Seleziona i video **più visti non ancora analizzati**, ordina per views.
- Invoca `claude -p` nella cartella `cowork/` (legge `CLAUDE.md`), passando **un solo
  transcript per chiamata** via stdin.
- Salvataggio **incrementale**: ogni video analizzato viene marcato (`analyzed_on`) e
  aggiunto a `cowork_analysis.json` subito → se interrompi, il progresso resta.
- Le chiamate fallite (timeout / output non-JSON) **non** marcano il video, che rientra
  alla run successiva.
- `sonnet` costa molto meno di Opus a parità di qualità d'analisi.

### 4. Report HTML
```powershell
python build_report.py
```
Apri `data/report.html` (doppio click). Contiene: statistiche, cruscotto driver
(frequenza + trend medio), elenco filtrabile/ordinabile dei video analizzati con
dettaglio (sintesi, driver+evidenze, citazioni, temi emergenti) e il backlog dei
video raccolti non ancora analizzati.

**Riesegui `build_report.py` dopo ogni nuova raccolta o analisi** per aggiornare l'HTML.

---

## Ciclo tipico di aggiornamento

```powershell
python monitor.py            # raccoglie i nuovi video pubblicati
python analyze_cowork.py --model sonnet   # analizza i nuovi più rilevanti
python build_report.py       # aggiorna il report
```

---

## Configurazione (soglie)

In testa a `monitor.py`:
- `SEARCH_N` — risultati per ricerca (default 25)
- `MIN_VIEWS` — soglia "poco visti" (default 200)
- `YEAR_DAYS` — ampiezza finestra temporale (default 365)
- `SUB_LANGS` — lingue sottotitoli preferite (default `it.*,en.*`)

In testa a `analyze_cowork.py`:
- `DEFAULT_LIMIT` — quanti video per run (default 10)

---

## Note e limiti

- **Ricerca non deterministica**: YouTube varia ordine/risultati tra run; `--n` più alto
  = copertura migliore.
- **Transcript non garantiti**: se assenti/disabilitati, `transcript_status` ≠ `ok`; il
  video resta nei risultati e l'analisi userà titolo/descrizione con `confidence: low`.
- **Falsi positivi tematici**: la ricerca per parole chiave può pescare video fuori tema;
  è l'analisi LLM a confermarne o scartarne la pertinenza leggendo il transcript.
- **Costi**: le analisi consumano usage Claude. Opus dà la qualità migliore ma costa di
  più; `--model sonnet` è il compromesso consigliato per lotti ampi.
- **"Ultimo anno"**: nelle query del browser (`build_queries.py`) il filtro nativo YouTube
  è "Quest'anno" (da inizio anno solare); in `monitor.py` è invece un trailing di 365 giorni
  esatti applicato sui dati reali.

---

## Roadmap

- Web app locale per sfogliare/filtrare i risultati e lanciare run dall'interfaccia
  (oggi: report HTML statico + script da riga di comando).
- Tracciamento del **trend nel tempo** per driver (più run nel tempo → serie storica).
