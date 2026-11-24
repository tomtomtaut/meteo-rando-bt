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
TZL = timezone(timedelta(hours=-4))


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
        faded = ' faded' if hr.get("src") == "ECMWF" else ''
        cells.append(f'<span class="h{faded}" style="background:{col}" title="{escape(tip)}"></span>')

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
        <p class="small muted">{escape(x['texte'])}{tendance}</p>
      </div>"""


def sommets_block(d: dict) -> str:
    if not d.get("sommets"):
        return ""
    rows = "".join(sommet_row(x) for x in d["sommets"])
    return (f'<details open><summary><b>Sommets</b></summary><div class="som">'
            f'<div class="ticks"><span>{FIRST_H}h</span><span>12h</span><span>{LAST_H}h</span></div>{rows}</div></details>')


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
        out.append(f"""
    <div class="cam">
      <iframe src="https://webcams.windy.com/webcams/public/embed/player/{wid}/day" loading="lazy"
        title="{escape(w['titre'])}" allowfullscreen></iframe>
      <p class="small">{escape(w['titre'])} · <a href="https://www.windy.com/webcams/{wid}">ouvrir sur Windy</a></p>
    </div>""")
    if not out:
        return ""
    return f"<details open><summary><b>Webcam</b> (dernières 24 h)</summary>{''.join(out)}</details>"


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

    head_cells = "".join(f"<th>{escape(d['short'])}</th>" for d in report["days"])
    rows = []
    for i, spot in enumerate(report["spots"]):
        cells = []
        for d in report["days"]:
            r = d["all"][i][1]
            start = f"<br><small>{r['start']}</small>" if r.get("start") and not r.get("nogo") else ""
            cells.append(f"<td>{chip(r)}{start}</td>")
        rows.append(f"<tr><td class='name'>{escape(spot['nom'])}</td>{''.join(cells)}</tr>")

    warn = "".join(f'<p class="bad">{escape(w)}</p>' for w in report["warnings"])
    exclus = "".join(f"<li>{escape(e['nom'])} : {escape(e['raison'])}</li>" for e in report["exclus"])

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Où sortir en Basse-Terre</title>
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
  .strip .faded {{ opacity:.4; }}
  .tag {{ font-size:.72rem; border:1px solid currentColor; border-radius:6px; padding:0 5px; color:var(--muted); }}
  .tag.ok {{ color:#1f9d55; }}
  .sit {{ background:var(--card); border-radius:12px; padding:10px 14px; margin:8px 0; font-size:.9rem; }}
  .sit ul {{ margin:.3em 0 0; padding-left:1.1em; }} .sit li {{ margin:.25em 0; }}
</style></head>
<body><main>
  <h1>Où sortir en Basse-Terre</h1>
  <p class="meta">Rapport du {escape(report['generated'])} · {escape(report['sources'])}</p>
  {warn}
  <h2>Les pépites</h2>
  {pepites(report)}
  {webcams(report)}
  <p class="legend">{legend()}</p>
  {''.join(days_html)}
  <h2>Toutes les activités</h2>
  <div class="table"><table><tr><th></th>{head_cells}</tr>{''.join(rows)}</table></div>
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
    <p><b>Sommets.</b> Profil vertical AROME (humidité et fraction nuageuse sur 19 niveaux) au-dessus du sommet,
    interpolé à son altitude réelle (le relief du modèle est lissé, donc trop bas). Dans le nuage : nuage ≥ 50 % ou
    humidité ≥ 95 %. Dégagé : nuage &lt; 20 % et humidité &lt; 88 %. « Au-dessus des nuages » : dégagé au sommet avec
    une couche nuageuse plus bas côté au vent. Les niveaux de pression sont espacés de 250 à 500 m : l'altitude exacte
    de la base et du sommet des nuages est approximative. Au-delà d'AROME, l'état est estimé grossièrement
    (humidité vers 1 500 m et nuages bas ECMWF, seuils sévères) : simple tendance.</p>
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
</main></body></html>
"""
