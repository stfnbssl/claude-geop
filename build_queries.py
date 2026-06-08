"""Genera stringhe di ricerca YouTube dai driver di attenzione.

Per ogni driver costruisce una query nello stile usato in precedenza:
    "geopolitica" AND ("kw1" OR "kw2" OR ...)
e l'URL completo di youtube.com/results con il filtro upload "Quest'anno"
(sp=EgIIBQ%3D%3D) gia' applicato. Produce anche una query "master" che unisce
in OR un termine-guida per ciascun driver.

Output in geop\\data\\:
    drivers_youtube_queries.json   (programmatico)
    drivers_youtube_queries.md     (leggibile, link cliccabili)
"""
import json, os
from urllib.parse import quote

SRC = r"C:\my\projects\geop\data\drivers_di_attenzione.json"
DATA_DIR = r"C:\my\projects\geop\data"

# Filtro "data di caricamento = Quest'anno" (il piu' vicino a 'ultimo anno' su YouTube)
SP_THIS_YEAR = "EgIIBQ%3D%3D"
ANCHOR = "geopolitica"

# Termine-guida (headline) per la query master: una frase distintiva per driver.
HEADLINE = {
    "D01": "fine dell'impero americano",
    "D02": "crisi della NATO",
    "D03": "controllo degli stretti",
    "D04": "armi autonome",
    "D05": "rivoluzione demografica",
    "D06": "guerra perpetua",
    "D07": "Trump Putin Netanyahu",
    "D08": "religione e potere",
    "D09": "autonomia strategica europea",
    "D10": "Turchia potenza regionale",
    "D11": "Cina opportunità",
    "D12": "Italia Mediterraneo Medioceania",
}


def quote_term(t):
    """Termine sempre tra virgolette: forza il match esatto su YouTube."""
    return f'"{t}"'


def or_group(terms):
    return "(" + " OR ".join(quote_term(t) for t in terms) + ")"


def build_url(query):
    return (f"https://www.youtube.com/results?search_query={quote(query)}"
            f"&sp={SP_THIS_YEAR}")


def main():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    drivers = data["driver_di_attenzione"]

    per_driver = []
    for d in drivers:
        kws = d["parole_chiave_associate"]
        query = f'"{ANCHOR}" AND {or_group(kws)}'
        per_driver.append({
            "id": d["id"],
            "nome": d["nome"],
            "query": query,
            "url": build_url(query),
            # nome file in cui salvare la pagina di risultati per parse_youtube.py
            "salva_come": f"youtube driver {d['id']}.md",
        })

    # Query master: anchor AND (OR di tutti gli headline)
    headlines = [HEADLINE.get(d["id"], d["nome"]) for d in drivers]
    master_query = f'"{ANCHOR}" AND {or_group(headlines)}'
    master = {"query": master_query, "url": build_url(master_query)}

    out_json = os.path.join(DATA_DIR, "drivers_youtube_queries.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "fonte": data.get("fonte"),
            "generato_il": "2026-06-02",
            "filtro_temporale": "YouTube upload = Quest'anno (sp=EgIIBQ%3D%3D)",
            "nota": "YouTube non supporta filtri data testuali: il periodo e' nel parametro URL sp.",
            "master": master,
            "per_driver": per_driver,
        }, f, ensure_ascii=False, indent=2)

    # Markdown leggibile
    lines = [
        "# Query YouTube - Driver di attenzione",
        "",
        f"**Fonte:** {data.get('fonte')}  ",
        "**Filtro temporale:** upload = *Quest'anno* (`sp=EgIIBQ%3D%3D`) — il piu' vicino a 'ultimo anno'.",
        "",
        "## Query master (tutti i driver in OR)",
        "",
        "```",
        master_query,
        "```",
        f"[Apri su YouTube]({master['url']})",
        "",
        "> Nota: una query con molti OR e' poco affidabile su YouTube. Per il monitoraggio",
        "> periodico usa le query per-driver qui sotto, una alla volta.",
        "",
        "## Query per driver",
        "",
    ]
    for p in per_driver:
        lines += [
            f"### {p['id']} — {p['nome']}",
            "",
            "```",
            p["query"],
            "```",
            f"[Apri su YouTube]({p['url']})  ",
            f"Salva la pagina come: `{p['salva_come']}` (poi `python parse_youtube.py`)",
            "",
        ]
    out_md = os.path.join(DATA_DIR, "drivers_youtube_queries.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generate {len(per_driver)} query per-driver + 1 master")
    print(f"-> {out_json}")
    print(f"-> {out_md}")


if __name__ == "__main__":
    main()
