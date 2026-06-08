# Handoff per Cowork — Analisi driver di attenzione (geopolitica)

## Contesto
Sto monitorando 12 **driver di attenzione** geopolitici (framework derivato da un
intervento di Lucio Caracciolo). Una pipeline Python (`monitor.py`) cerca su YouTube
i video pertinenti dell'ultimo anno, ne estrae i metadati esatti e scarica i transcript.
Il tuo compito è l'analisi **semantica** di ciascun video: capire quali driver vengono
realmente trattati e con quale segnale — un lavoro che il programma NON fa di proposito.

## Input (tutti in `C:\my\projects\geop\data\`)
1. **`drivers_di_attenzione.json`** — definizione dei 12 driver. Per ognuno: `id`, `nome`,
   `categoria`, `descrizione_breve`, **`manifestazioni_osservabili`** (eventi concreti da
   cercare), `parole_chiave_associate`. **Leggilo per primo**: è il riferimento per l'analisi.
2. **`monitor_results.json`** — i 150 video tenuti. Per ognuno: `video_id`, `title`, `url`,
   `published`, `views_count`, `duration_seconds`, `channel`, `description`,
   `found_via_query` (driver la cui *ricerca* ha pescato il video — è un indizio, NON una
   conferma), `transcript_status`, `transcript_lang`, `transcript_file`.
3. **`transcripts\<id>.<lang>.txt`** — il testo del video. È la fonte primaria dell'analisi.

## Compito (per ogni video di `monitor_results.json`)
1. Apri il transcript indicato in `transcript_file` (se `transcript_status` ≠ `"ok"` non
   c'è transcript: analizza solo da `title` + `description` e segna `analysis_confidence: "low"`).
2. Stabilisci quali dei **12 driver** sono *effettivamente trattati* nel contenuto
   (analisi semantica, non keyword). `found_via_query` è solo un suggerimento: confermalo
   o scartalo. I falsi positivi sono attesi (es. "Suez" in un video su voli aerei → NON è D03).
3. Per ogni driver confermato, compila i campi dello schema sotto, **citando il transcript**.
4. Annota temi rilevanti che NON rientrano nei 12 driver in `temi_emergenti` (possibili nuovi driver).

## Regole
- **Ancorati alle prove**: ogni driver rilevato deve avere un `evidenza` (citazione o
  parafrasi puntuale dal transcript). Se non trovi evidenza, non assegnare il driver.
- **Niente invenzioni**: non dedurre posizioni non espresse. Se il transcript è ambiguo,
  abbassa `rilevanza` e annotalo in `note`.
- `valutazione_trend` segue le note metodologiche del framework: da **-3** (il driver
  *peggiora*/accelera verso la crisi) a **+3** (si attenua/si risolve), `0` = neutro/descrittivo.
- `rilevanza`: **0** (assente) – **1** (citato di sfuggita) – **2** (tema secondario) –
  **3** (tema centrale del video). Includi nello schema solo driver con rilevanza ≥ 1.
- `manifestazioni_rilevate`: scegli SOLO dalla lista `manifestazioni_osservabili` del driver
  in `drivers_di_attenzione.json`; se ne emerge una nuova, mettila in `note`.

## Schema di output (un oggetto per video) → salva in `data\cowork_analysis.json`
```json
{
  "video_id": "string",
  "title": "string",
  "url": "string",
  "published": "YYYY-MM-DD",
  "channel": "string",
  "analysis_confidence": "high | medium | low",
  "sintesi": "2-3 frasi sul contenuto del video",
  "matched_drivers": [
    {
      "driver_id": "Dxx",
      "rilevanza": 0,
      "valutazione_trend": 0,
      "manifestazioni_rilevate": ["testo esatto preso dalla lista del driver"],
      "evidenza": "citazione o parafrasi puntuale dal transcript",
      "contesto": "facoltativo: minuto/sezione o breve contesto"
    }
  ],
  "entita_chiave": {
    "persone": [],
    "luoghi": [],
    "organizzazioni": []
  },
  "citazioni_notevoli": ["frasi testuali significative dal transcript"],
  "temi_emergenti": ["temi rilevanti fuori dai 12 driver"],
  "note": "falsi positivi scartati, ambiguità, manifestazioni nuove, ecc."
}
```

Output finale: un array JSON di questi oggetti in `C:\my\projects\geop\data\cowork_analysis.json`.

## Suggerimento di lavorazione
Procedi a lotti (es. per `found_via_query` o per canale), dando priorità ai video con più
`views_count`. Per i video lunghi, leggi l'intero transcript ma cita solo i passaggi rilevanti.
Mantieni i `driver_id` coerenti con `drivers_di_attenzione.json`.
