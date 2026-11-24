"""Génération de la page HTML du rapport (un seul fichier, lisible sur téléphone)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape

from .sommets import STATES, FIRST_H, LAST_H

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
COLORS = {"Top": "#1f9d55", "Bien": "#7cb342", "Moyen": "#f0a500", "À éviter": "#e06c3c", "Non": "#b3261e"}
SOURCE_NAMES = {"AROME": "AROME 2,5 km", "ECMWF-ens": "ensemble ECMWF (probabilités, maille ~25 km)",
                "ECMWF": "ECMWF seul (maille ~9-25 km)", "—": "pas de donnée"}
from .heure import TZ as TZL  # noqa: E402


def coverage(merged, d: date) -> str:
    """Quel modèle couvre quelles heures de la journée (5h-20h)."""
    segs = []
    for h in range(5, 21):
        t = datetime(d.year, d.month, d.day, h, tzinfo=TZL).astimezone(timezone.utc)
        ti = merged.index.get(t)
        src = merged.source[ti] if ti is not None else "—"
        if segs and segs[-1][0] == src:
            segs[-1][2] = h
        else:
            segs.append([src, h, h])
    parts = [f"{SOURCE_NAMES.get(src, src)} de {a}h à {b + 1}h" for src, a, b in segs]
    return " · ".join(parts)


def fdate(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def chip(r: dict, with_score: bool = True) -> str:
    lab = r.get("label") or "—"
    txt = lab if not with_score or r.get("nogo") or r.get("score") is None else f"{lab} · {r['score']}"
    return f'<span class="chip" style="background:{COLORS.get(lab, "#999")}">{escape(txt)}</span>'


CAT_NAMES = {"rando": "Randos", "riviere": "Rivières", "sommet": "Sommets",
             "mer": "Mer calme", "surf": "Surf", "kite": "Kite / wing"}


def cat_of(spot: dict) -> str:
    if spot["type"] == "mer":
        return {"calme": "mer", "surf": "surf", "kite": "kite"}.get(spot.get("mer"), "mer")
    return "riviere" if spot["type"] == "riviere" else ("sommet" if spot.get("_high") else "rando")


def rank_card(spot: dict, r: dict, d: dict, i_day: int) -> str:
    """Carte du mode Classement (une activité pour un jour), avec ses attributs de filtre."""
    score = -1 if r.get("score") is None else (0 if r.get("nogo") else r["score"])
    when = (f"Départ {r['start']} → retour vers {r['end']}" if r.get("start") and not r.get("nogo") else "")
    acces = f'<p class="warn">⚠ {escape(spot["acces"])}</p>' if spot.get("acces") else ""
    src = {"AROME": "AROME", "mixte": "AROME + ECMWF", "ECMWF-ens": "tendance ECMWF", "ECMWF": "tendance ECMWF"}
    return f"""
    <article class="card rk" data-day="{i_day}" data-cat="{cat_of(spot)}" data-ile="{escape(spot.get('ile', ''))}" data-score="{score}">
      <div class="row"><h3>{escape(spot['nom'])}</h3>{chip(r)}</div>
      <p class="when">{escape(d['title'])}{' · ' + when if when else ''}</p>
      <p class="small muted">{escape(spot.get('ile', ''))} · {escape(spot['secteur'])} · {escape(CAT_NAMES[cat_of(spot)])} · {escape(spot['niveau'])} · {escape(src.get(r.get('source'), ''))}</p>
      <p>{escape(' · '.join(r.get('reasons', [])))}</p>{acces}
    </article>"""


def card(spot: dict, r: dict) -> str:
    acces = f'<p class="warn">⚠ {escape(spot["acces"])}</p>' if spot.get("acces") else ""
    conseil = f'<p class="hint">{escape(spot["conseil"])}</p>' if spot.get("conseil") else ""
    return f"""
    <article class="card">
      <div class="row"><h3>{escape(spot['nom'])}</h3>{chip(r)}</div>
      <p class="when">Départ {r['start']} → retour vers {r['end']} · <span class="muted">{escape(spot['secteur'])}</span></p>
      <p>{escape(' · '.join(r['reasons']))}</p>{conseil}{acces}
    </article>"""


def sommet_row(x: dict) -> str:
    cells = []
    for hr in x["hours"]:
        lab, col = STATES.get(hr["state"], STATES[None])
        det = hr.get("det") or {}
        tip = f"{hr['h']}h : {lab}" + (f" (nuage {det['cc']} %, humidité {det['rh']} %)" if det.get("cc") is not None else "")
        if det.get("base") is not None:
            haut = "pas de plafond net" if det.get("haut") == 9999 else (f"~{det['haut']:.0f} m" if det.get("haut") is not None else "?")
            tip += f" · couche nuageuse : base ~{det['base']:.0f} m, haut {haut}"
        faded = ' faded' if hr.get("src") == "ECMWF" else ''
        cells.append(f'<span class="h{faded}" style="background:{col}" data-tip="{escape(tip)}">{hr["h"]}</span>')

    def sun(icon, s):
        mark = '<b class="ok">✓</b>' if s["top"] else '<span class="no">✗</span>'
        hz = "" if s["horizon"] is None else ("" if s["horizon"] else " (horizon bouché)")
        return f"{icon} {s['heure']} {mark}{hz}"

    tendance = " · tendance ECMWF" if x["source"] == "ECMWF" else ""
    return f"""
      <div class="srow">
        <div class="row"><span><b>{escape(x['nom'])}</b> <span class="muted">{x['alt']} m</span></span>
          <span class="small">{sun('🌅', x['lever'])} &nbsp; {sun('🌇', x['coucher'])}</span></div>
        <div class="strip">{''.join(cells)}</div>
        <p class="small tipline">Survole ou touche une heure pour le détail.</p>
        <p class="small muted">{escape(x['texte'])}{tendance}</p>
      </div>"""


def sommets_block(d: dict) -> str:
    if not d.get("sommets"):
        return ""
    rows = "".join(sommet_row(x) for x in d["sommets"])
    return (f'<details open><summary><b>Sommets</b></summary><div class="som">'
            f'<div class="ticks"><span>{FIRST_H}h</span><span>12h</span><span>{LAST_H}h</span></div>{rows}</div></details>')


def pepites_list(report: dict) -> list[dict]:
    """Pépites en données (pour la carte) : [{jour, texte, fiable}]."""
    out = []
    for d in report["days"]:
        day = d["title"].split(" · ")[1]
        for kind, key in (("Lever", "lever"), ("Coucher", "coucher")):
            names = [x for x in d.get("sommets", []) if x[key]["top"]]
            if names:
                out.append({"jour": day, "texte": f"{kind.lower()} {names[0][key]['heure']} dégagé : "
                            + ", ".join(x["nom"] for x in names),
                            "fiable": any(x[key].get("src") == "AROME" for x in names)})
    return out


def pepites(report: dict) -> str:
    items = []
    for d in report["days"]:
        day = escape(d["title"].split(" · ")[1])
        for kind, key in (("Lever", "lever"), ("Coucher", "coucher")):
            names = [x for x in d.get("sommets", []) if x[key]["top"]]
            if names:
                tendance = all(x[key].get("src") != "AROME" for x in names)
                tag = ' <span class="tag">tendance ECMWF, peu fiable</span>' if tendance else ' <span class="tag ok">AROME</span>'
                items.append(f"<li><b>{day}</b> · {kind.lower()} {names[0][key]['heure']} dégagé : "
                             f"{escape(', '.join(x['nom'] for x in names))}{tag}</li>")
        long_clear = [x for x in d.get("sommets", []) if "Dégagé de" in x["texte"]]
        if long_clear and not any(x["lever"]["top"] for x in d.get("sommets", [])):
            x = long_clear[0]
            items.append(f"<li><b>{day}</b> · {escape(x['nom'])} : {escape(x['texte'])}</li>")
    if not items:
        return '<p class="muted">Pas de fenêtre dégagée prévue sur les sommets dans les 3 jours.</p>'
    return f"<ul class='pep'>{''.join(items)}</ul>"


def webcams(report: dict) -> str:
    out = []
    for w in report.get("webcams", []):
        wid = escape(str(w["id"]))
        src = escape(w.get("player") or f"https://webcams.windy.com/webcams/public/embed/player/{wid}/day")
        lien = escape(w.get("lien") or f"https://www.windy.com/webcams/{wid}")
        out.append(f"""
    <div class="cam">
      <iframe src="{src}" loading="lazy" title="{escape(w['titre'])}" allowfullscreen></iframe>
      <p class="small">{escape(w['titre'])} · <a href="{lien}">ouvrir sur Windy</a></p>
    </div>""")
    if not out:
        return ""
    return (f"<details open><summary><b>Webcams</b> ({len(out)}, dernières 24 h, Windy)</summary>"
            f"<div class='cams'>{''.join(out)}</div></details>")


def legend() -> str:
    return "".join(f'<span class="lg"><span class="h" style="background:{c}"></span>{escape(l)}</span>'
                   for k, (l, c) in STATES.items() if k)


def page(report: dict) -> str:
    days_html = []
    for d in report["days"]:
        tops = d["top"]
        best_score = tops[0][1]["score"] if tops else 0
        intro = ""
        if not tops:
            intro = '<p class="bad">Rien de praticable selon le modèle : journée à garder pour autre chose.</p>'
        elif best_score < 55:
            intro = '<p class="bad">Journée médiocre partout. Les moins mauvaises options :</p>'
        bad = [(s, r) for s, r in d["all"] if r.get("nogo") or (r.get("score") or 0) < 35]
        bad_html = "".join(
            f"<li><b>{escape(s['nom'])}</b> {chip(r, False)} — {escape(' · '.join(r['reasons']))}</li>" for s, r in bad
        )
        sit = d.get("situation") or {}
        sit_html = ""
        if sit.get("texte"):
            src_sit = "profils AROME" if sit.get("source") == "AROME" else "ECMWF, sans profil fin"
            sit_html = (f'<div class="sit"><b>Situation</b> <span class="muted">({src_sit}, 6h-16h)</span>'
                        f'<ul>{"".join(f"<li>{escape(t)}</li>" for t in sit["texte"])}</ul></div>')
        days_html.append(f"""
  <section>
    <h2>{escape(d['title'])}</h2>
    <p class="conf">Prévision : {escape(d.get('couverture', ''))}</p>
    {sit_html}
    {intro}
    {''.join(card(s, r) for s, r in tops)}
    {f'<details><summary>À éviter ({len(bad)})</summary><ul>{bad_html}</ul></details>' if bad else ''}
    {sommets_block(d)}
  </section>""")

    head_cells = "".join(f'<th class="sortable" data-k="{k}">{escape(d["short"])} ↕</th>'
                         for k, d in enumerate(report["days"]))
    rows = []
    for i, spot in enumerate(report["spots"]):
        cells, attrs = [], []
        for k, d in enumerate(report["days"]):
            r = d["all"][i][1]
            sc = -1 if r.get("score") is None else (0 if r.get("nogo") else r["score"])
            attrs.append(f'data-s{k}="{sc}"')
            start = f"<br><small>{r['start']}</small>" if r.get("start") and not r.get("nogo") else ""
            cells.append(f"<td>{chip(r)}{start}</td>")
        rows.append(f'<tr class="tr" data-cat="{cat_of(spot)}" data-ile="{escape(spot.get("ile", ""))}" {" ".join(attrs)}>'
                    f"<td class='name'>{escape(spot['nom'])}<br><small class='muted'>{escape(spot.get('ile', ''))}"
                    f" · {escape(CAT_NAMES[cat_of(spot)])}</small></td>{''.join(cells)}</tr>")
    iles = sorted({s.get("ile", "") for s in report["spots"]}, key=lambda x: (x == "Mer", x))
    ile_btns = "".join(f'<button class="chip" data-i="{escape(x)}">{escape(x)}</button>' for x in iles)

    warn = "".join(f'<p class="bad">{escape(w)}</p>' for w in report["warnings"])
    day_btns = "".join(f'<button class="chip" data-d="{i}">{escape(d["title"].split(" · ")[0])}</button>'
                       for i, d in enumerate(report["days"]))
    cat_btns = "".join(f'<button class="chip" data-c="{k}">{v}</button>' for k, v in CAT_NAMES.items())
    rank_cards = "".join(rank_card(s, r, d, i) for i, d in enumerate(report["days"]) for s, r in d["all"])
    exclus = "".join(f"<li>{escape(e['nom'])} : {escape(e['raison'])}</li>" for e in report["exclus"])

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Où sortir en Guadeloupe</title>
<style>
  :root {{ --bg:#f6f5f1; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --fg:#ecebe6; --muted:#9c9b95; --card:#1f1f1d; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.45 -apple-system, system-ui, sans-serif; background:var(--bg); color:var(--fg); }}
  main {{ max-width:760px; margin:0 auto; padding:16px; }}
  h1 {{ font-size:1.5rem; margin:.2em 0; }} h2 {{ font-size:1.2rem; margin:1.6em 0 .2em; }}
  h3 {{ font-size:1rem; margin:0; }}
  .meta, .muted, .conf {{ color:var(--muted); font-size:.85rem; margin:.2em 0 .8em; }}
  .card {{ background:var(--card); border-radius:12px; padding:12px 14px; margin:10px 0; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .card p {{ margin:.3em 0; }}
  .row {{ display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }}
  .when {{ font-weight:600; }}
  .chip {{ color:#fff; border-radius:999px; padding:2px 9px; font-size:.78rem; font-weight:600; white-space:nowrap; }}
  .warn {{ color:#b06000; font-size:.85rem; }} .hint {{ color:var(--muted); font-size:.85rem; }}
  .bad {{ color:#b3261e; }}
  details {{ margin:8px 0; }} summary {{ cursor:pointer; color:var(--muted); }}
  details li {{ margin:.4em 0; font-size:.9rem; }}
  .table {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:.85rem; }}
  td, th {{ padding:6px 4px; border-bottom:1px solid rgba(128,128,128,.2); text-align:center; vertical-align:top; }}
  td.name {{ text-align:left; }}
  footer {{ color:var(--muted); font-size:.8rem; margin-top:2em; }}
  .som {{ background:var(--card); border-radius:12px; padding:10px 14px; margin:8px 0; }}
  .srow {{ margin:10px 0 4px; }} .srow .row {{ align-items:baseline; flex-wrap:wrap; }}
  .ok {{ color:#1f9d55; }} .no {{ color:var(--muted); }}
  .strip {{ display:flex; gap:2px; margin:6px 0 2px; }}
  .strip .h {{ flex:1; height:16px; border-radius:3px; }}
  .ticks {{ display:flex; justify-content:space-between; font-size:.7rem; color:var(--muted); }}
  .small {{ font-size:.85rem; margin:.3em 0; }}
  .legend {{ font-size:.75rem; color:var(--muted); }}
  .lg {{ margin-right:10px; white-space:nowrap; }}
  .lg .h {{ display:inline-block; width:12px; height:12px; border-radius:3px; vertical-align:-1px; margin-right:4px; }}
  .pep li {{ margin:.3em 0; }}
  .cam iframe {{ width:100%; height:240px; border:0; border-radius:12px; }}
  .cams {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:10px; }}
  .strip .faded {{ opacity:.4; }}
  .tag {{ font-size:.72rem; border:1px solid currentColor; border-radius:6px; padding:0 5px; color:var(--muted); }}
  .tag.ok {{ color:#1f9d55; }}
  .sit {{ background:var(--card); border-radius:12px; padding:10px 14px; margin:8px 0; font-size:.9rem; }}
  .sit ul {{ margin:.3em 0 0; padding-left:1.1em; }} .sit li {{ margin:.25em 0; }}
  .strip .h {{ color:#fff; font-size:.62rem; font-weight:600; display:flex; align-items:center; justify-content:center;
    height:18px; cursor:pointer; text-shadow:0 0 2px rgba(0,0,0,.4); }}
  .strip .h.sel {{ outline:2px solid var(--fg); }}
  .tipline {{ min-height:1.2em; color:var(--fg); }}
  .bar {{ display:flex; flex-direction:column; gap:6px; margin:10px 0; }}
  .chips {{ display:flex; gap:6px; overflow-x:auto; }}
  .bar .chip, #views .chip {{ border:1px solid rgba(128,128,128,.3); background:var(--card); color:var(--fg); border-radius:999px;
    padding:5px 11px; font-size:.85rem; white-space:nowrap; cursor:pointer; font-weight:400; }}
  .bar .chip.on, #views .chip.on {{ background:#1f6f4a; border-color:#1f6f4a; color:#fff; }}
  .nav a {{ color:inherit; }}
  th.sortable {{ cursor:pointer; white-space:nowrap; }} th.sortable.on {{ color:#1f6f4a; text-decoration:underline; }}
  tr[hidden] {{ display:none; }}
</style></head>
<body><main>
  <p class="nav"><a href="index.html">Carte</a> · <b>Liste</b></p>
  <h1>Où sortir en Guadeloupe</h1>
  <p class="meta">Rapport du {escape(report['generated'])} · {escape(report['sources'])}</p>
  {warn}
  <div class="bar">
    <div class="chips" id="views"><button class="chip on" data-v="jour">Par jour</button><button class="chip" data-v="rank">Classement</button></div>
  </div>
  <div id="v-rank" hidden>
    <div class="bar">
      <div class="chips" id="f-day"><button class="chip on" data-d="all">Tous les jours</button>{day_btns}</div>
      <div class="chips" id="f-cat"><button class="chip on" data-c="all">Toutes</button>{cat_btns}</div>
      <div class="chips" id="f-ile"><button class="chip on" data-i="all">Toutes les îles</button>{ile_btns}</div>
      <label class="small"><input type="checkbox" id="f-hide" checked> masquer « À éviter » et « Non »</label>
    </div>
    <p class="small muted" id="rk-count"></p>
    <div id="rk-list">{rank_cards}</div>
  </div>
  <div id="v-jour">
  <h2>Les pépites</h2>
  {pepites(report)}
  {webcams(report)}
  <p class="legend">{legend()}</p>
  {''.join(days_html)}
  <h2>Toutes les activités</h2>
  <div class="bar">
    <div class="chips" id="t-cat"><button class="chip on" data-c="all">Toutes</button>{cat_btns}</div>
    <div class="chips" id="t-ile"><button class="chip on" data-i="all">Toutes les îles</button>{ile_btns}</div>
    <p class="small muted">Touche un jour dans l'en-tête du tableau pour trier du mieux noté au moins bien noté.</p>
  </div>
  <div class="table"><table id="tbl"><tr><th>Activité</th>{head_cells}</tr>{''.join(rows)}</table></div>
  </div>
  <footer>
    <h2>Comment c'est calculé, et ce qui reste approximatif</h2>
    <p><b>Modèles.</b> AROME Outre-Mer Antilles (Météo-France, maille 2,5 km) : le seul modèle qui voit le relief de la
    Basse-Terre ; il va jusqu'à 48 h après son heure de calcul. Au-delà : ECMWF (Open-Meteo), maille 9 à 25 km, qui voit
    l'île comme une bosse. La ligne « Prévision » de chaque jour indique quelles heures viennent de quel modèle.
    Les heures ECMWF sont pâlies sur les barres des sommets.</p>
    <p><b>Pluie en probabilités.</b> Un modèle à 2,5 km place une averse tropicale à quelques km près. On lit donc les
    9 mailles autour de chaque point (±2,5 km), pour le dernier run AROME et le précédent : jusqu'à 18 scénarios par
    heure. La pluie retenue est le 70e percentile (90e en amont des rivières, par prudence), et le « risque d'averse »
    la part des scénarios à 0,5 mm/h ou plus. Au-delà d'AROME, les 51 scénarios de l'ensemble ECMWF.
    Ces pourcentages sont bruts : ils ne sont pas encore calibrés sur ce qui est réellement tombé.</p>
    <p><b>Sommets.</b> Le relief du modèle est lissé (sommets trop bas) et l'air libre qu'il simule ne subit pas le
    soulèvement forcé par le vrai relief : lu seul, il est trop optimiste. On place donc d'abord la couche nuageuse
    d'alizé sur l'air en amont (en mer, à l'est), selon la méthode utilisée pour les montagnes de Porto Rico :
    la <b>base</b> est le niveau de condensation par soulèvement (LCL) de l'air entre la surface et 500 m, formule
    d'Espy (125 m par °C d'écart entre température et point de rosée) ; le <b>haut</b> est le sommet de la couche
    humide (humidité &lt; 75 %), plafonnée par l'inversion des alizés. Un relief au vent entre la base et le haut
    est dans le nuage orographique ; à ±100 m du haut, incertain ; au-dessus, au-dessus des nuages ; sous la base,
    dégagé. Si le profil AROME à l'altitude réelle du sommet montre déjà du nuage (≥ 50 % ou humidité ≥ 95 %),
    il prime. Les niveaux de pression sont espacés de 250 à 500 m : l'altitude exacte
    de la base et du sommet des nuages est approximative. Au-delà d'AROME, l'état est estimé grossièrement
    (humidité vers 1 500 m et nuages bas ECMWF, seuils sévères) : simple tendance.</p>
    <p><b>Mer.</b> Vagues et houle : Open-Meteo Marine (modèles de vagues Météo-France et ECMWF), cases de 5,5 km.
    Vent à 10 m : AROME. Mer calme (kayak, snorkeling, plongée, traversée) : creux &lt; 0,6 m et vent &lt; 15 km/h pour
    un score plein. Surf : houle de 1,2 à 2,5 m, période ≥ 9 s, et orientation de la houle propre à chaque spot.
    Kite / wing : vent établi de 22 à 45 km/h, sans rafales trop irrégulières. Près des côtes, les baies abritées
    peuvent être plus calmes que la case ne l'indique.</p>
    <p><b>Îles plates.</b> Grande-Terre, Marie-Galante, Désirade : pas de pluie de relief ; les averses viennent de
    l'alizé ou de la chaleur l'après-midi. La chaleur pèse dans le score des sentiers exposés (dès 30 °C).</p>
    <p><b>Situation.</b> Lue sur la colonne d'air en mer à l'est de l'île, dans l'alizé non perturbé : force de l'alizé
    vers 1 000 m, hauteur de la couche humide (cumulus d'alizé), humidité vers 3 000 m, poussières sahariennes (CAMS).
    Les règles d'interprétation (alizé fort = pluie au vent et abri sous le vent ; alizé faible = averses thermiques
    l'après-midi) viennent des études de terrain sur la Guadeloupe et la Dominique.</p>
    <p><b>Lever et coucher.</b> Calculés pour l'altitude du sommet. L'horizon est jugé sur les nuages bas et moyens
    en mer (à l'est au lever, à l'ouest au coucher).</p>
    <p><b>Limites.</b> Les seuils sont des valeurs de départ, à ajuster avec la webcam et vos sorties. Les coordonnées
    des spots sont approximatives. Un grain local peut toujours passer entre les mailles.</p>
    <p><b>Avant de partir :</b> vigilance sur <a href="https://meteofrance.gp">meteofrance.gp</a>
    et état des sentiers sur <a href="https://www.randoguadeloupe.gp">randoguadeloupe.gp</a>.</p>
    {f'<p>Non proposées :</p><ul>{exclus}</ul>' if exclus else ''}
  </footer>
</main>
<script>
// Bascule Par jour / Classement
const views = document.querySelectorAll("#views .chip");
views.forEach(b => b.onclick = () => {{
  views.forEach(x => x.classList.toggle("on", x === b));
  document.getElementById("v-rank").hidden = b.dataset.v !== "rank";
  document.getElementById("v-jour").hidden = b.dataset.v === "rank";
}});
// Filtres et tri du classement
const f = {{d: "all", c: "all", i: "all"}};
function apply() {{
  const hide = document.getElementById("f-hide").checked;
  const list = document.getElementById("rk-list");
  const cards = [...list.querySelectorAll(".rk")];
  cards.sort((a, b) => +b.dataset.score - +a.dataset.score).forEach(c => list.appendChild(c));
  let n = 0;
  cards.forEach(c => {{
    const ok = (f.d === "all" || c.dataset.day === f.d) && (f.c === "all" || c.dataset.cat === f.c)
      && (f.i === "all" || c.dataset.ile === f.i) && !(hide && +c.dataset.score < 35);
    c.hidden = !ok; if (ok) n++;
  }});
  document.getElementById("rk-count").textContent = n + " résultat" + (n > 1 ? "s" : "") + ", du mieux noté au moins bien noté";
}}
document.querySelectorAll("#f-day .chip").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#f-day .chip").forEach(x => x.classList.toggle("on", x === b)); f.d = b.dataset.d; apply(); }});
document.querySelectorAll("#f-cat .chip").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#f-cat .chip").forEach(x => x.classList.toggle("on", x === b)); f.c = b.dataset.c; apply(); }});
document.querySelectorAll("#f-ile .chip").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#f-ile .chip").forEach(x => x.classList.toggle("on", x === b)); f.i = b.dataset.i; apply(); }});
document.getElementById("f-hide").onchange = apply;
apply();
// Tableau « Toutes les activités » : filtres et tri par jour
const t = {{c: "all", i: "all", k: null}};
function applyTable() {{
  const tbl = document.getElementById("tbl"), rows = [...tbl.querySelectorAll("tr.tr")];
  if (t.k !== null) rows.sort((a, b) => +b.dataset["s" + t.k] - +a.dataset["s" + t.k]).forEach(r => tbl.appendChild(r));
  rows.forEach(r => r.hidden = !((t.c === "all" || r.dataset.cat === t.c) && (t.i === "all" || r.dataset.ile === t.i)));
  tbl.querySelectorAll("th.sortable").forEach(h => h.classList.toggle("on", +h.dataset.k === t.k));
}}
document.querySelectorAll("#t-cat .chip").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#t-cat .chip").forEach(x => x.classList.toggle("on", x === b)); t.c = b.dataset.c; applyTable(); }});
document.querySelectorAll("#t-ile .chip").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#t-ile .chip").forEach(x => x.classList.toggle("on", x === b)); t.i = b.dataset.i; applyTable(); }});
document.querySelectorAll("#tbl th.sortable").forEach(h => h.onclick = () => {{ t.k = +h.dataset.k; applyTable(); }});
t.k = 0; applyTable();
// Détail d'une heure sur les barres des sommets (survol ou toucher)
document.querySelectorAll(".srow").forEach(row => {{
  const line = row.querySelector(".tipline");
  row.querySelectorAll(".strip .h").forEach(c => {{
    const show = () => {{ row.querySelectorAll(".strip .h").forEach(x => x.classList.toggle("sel", x === c)); line.textContent = c.dataset.tip; }};
    c.onmouseenter = show; c.onclick = show;
  }});
}});
</script>
</body></html>
"""
