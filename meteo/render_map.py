"""Page principale : carte de la Basse-Terre avec les mailles AROME colorées par activité.

Page statique : le JavaScript lit grid.json (mailles) et data.json (activités, situation).
"""

from __future__ import annotations


def page() -> str:
    return r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Où sortir en Guadeloupe — carte</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root { --bg:#f6f5f1; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:rgba(128,128,128,.25); --acc:#1f6f4a; }
  @media (prefers-color-scheme: dark) { :root { --bg:#141413; --fg:#ecebe6; --muted:#9c9b95; --card:#1f1f1d; --acc:#5cc492; } }
  * { box-sizing:border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--fg);
    font:15px/1.4 -apple-system, system-ui, sans-serif; }
  .app { display:flex; flex-direction:column; min-height:100%; }
  header { padding:10px 12px 6px; }
  .top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  h1 { font-size:1.15rem; margin:0; }
  .switch a, .switch b { padding:4px 10px; border-radius:999px; font-size:.85rem; text-decoration:none; }
  .switch b { background:var(--fg); color:var(--bg); } .switch a { color:var(--fg); border:1px solid var(--line); }
  .meta { color:var(--muted); font-size:.75rem; margin:4px 0 0; } .meta summary { cursor:pointer; }
  .controls { padding:4px 12px 8px; display:flex; flex-direction:column; gap:7px; }
  .chips { display:flex; gap:6px; overflow-x:auto; }
  .chip { border:1px solid var(--line); background:var(--card); color:var(--fg); border-radius:999px; padding:5px 11px;
    font-size:.85rem; white-space:nowrap; cursor:pointer; }
  .chip.on { background:var(--acc); border-color:var(--acc); color:#fff; }
  .hour { display:flex; align-items:center; gap:10px; }
  .hour input { flex:1; accent-color:var(--acc); }
  .hour .lbl { min-width:118px; font-size:.85rem; }
  .src { font-size:.72rem; color:var(--muted); }
  .main { display:flex; flex-direction:column; flex:1; }
  #map { height:58vh; min-height:340px; }
  .panel { padding:10px 12px 30px; }
  @media (min-width: 900px) {
    .main { flex-direction:row; } #map { height:auto; flex:1.6; min-height:calc(100vh - 150px); }
    .panel { flex:1; max-height:calc(100vh - 150px); overflow-y:auto; }
  }
  .legend { display:flex; align-items:center; gap:6px; font-size:.72rem; color:var(--muted); }
  .grad { height:8px; flex:1; border-radius:4px; max-width:220px;
    background:linear-gradient(90deg,#b3261e,#e06c3c 30%,#f0a500 50%,#7cb342 70%,#1f9d55); }
  .card { background:var(--card); border-radius:12px; padding:10px 12px; margin:8px 0; box-shadow:0 1px 3px rgba(0,0,0,.07); }
  .card h3 { margin:0 0 4px; font-size:.95rem; }
  .row { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
  .pill { color:#fff; border-radius:999px; padding:1px 8px; font-size:.75rem; font-weight:600; white-space:nowrap; }
  .muted { color:var(--muted); } .small { font-size:.82rem; } .warn { color:#b06000; font-size:.8rem; }
  .item { padding:7px 0; border-bottom:1px solid var(--line); cursor:pointer; }
  .item:last-child { border-bottom:0; }
  ul { margin:.3em 0; padding-left:1.1em; } li { margin:.2em 0; }
  .tag { font-size:.7rem; border:1px solid currentColor; border-radius:6px; padding:0 4px; color:var(--muted); }
  .tag.ok { color:#1f9d55; }
  details summary { cursor:pointer; font-weight:600; }
  iframe.cam { width:100%; height:220px; border:0; border-radius:10px; margin-top:6px; }
  .leaflet-tooltip.tt, .leaflet-popup-content { font-size:.8rem; line-height:1.35; }
  .tt b { font-size:.85rem; }
  .bad { color:#b3261e; font-size:.82rem; }
  .q { display:inline-block; width:1.15em; height:1.15em; line-height:1.15em; text-align:center; border-radius:50%;
    border:1px solid currentColor; color:var(--acc); font-size:.7rem; font-weight:700; text-decoration:none; margin-left:3px; }
  .avis { border-left:4px solid var(--acc); }
  .kv { width:100%; border-collapse:collapse; font-size:.8rem; margin:.3em 0; }
  .kv td { padding:4px 3px; border-bottom:1px solid var(--line); vertical-align:top; }
  .kv td:first-child { width:36%; color:var(--muted); }
  .conf { color:#fff; border-radius:999px; padding:1px 8px; font-size:.75rem; font-weight:600; white-space:nowrap; }
  .camicon { font-size:18px; line-height:22px; text-align:center; background:none; border:0; }
</style></head>
<body><div class="app">
<header>
  <div class="top"><h1>Où sortir en Guadeloupe</h1>
    <span class="switch"><b>Carte</b> <a href="liste.html">Liste</a> <a href="apprendre.html" title="Apprendre à lire">?</a></span></div>
  <details class="meta"><summary id="meta">Chargement…</summary><span id="sources"></span></details>
</header>
<div class="controls">
  <div class="chips" id="days"></div>
  <div class="chips" id="cats"></div>
  <div class="hour"><input type="range" id="hour" min="0" max="14" step="1">
    <span class="lbl"><b id="hlabel"></b> <span class="src" id="hsrc"></span></span></div>
  <div class="legend">0 <span class="grad"></span> 100 · <span id="legend-txt"></span></div>
</div>
<div class="main">
  <div id="map"></div>
  <div class="panel" id="panel"></div>
</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const CATS = {
  rando:   {label: "Randos",   legend: "pluie, rafales, chaleur, orages à l'heure choisie"},
  riviere: {label: "Rivières", legend: "pluie des 24 h avant + pluie à l'heure (crues)"},
  sommet:  {label: "Sommets",  legend: "comme rando + nuage à l'altitude de la case"},
  mer:     {label: "Mer calme", legend: "kayak, snorkeling, plongée : petite mer, peu de vent"},
  surf:    {label: "Surf",     legend: "houle : hauteur et période (orientation jugée sur les spots)"},
  kite:    {label: "Kite / wing", legend: "vent établi 22-45 km/h, rafales régulières"},
};
const SRC = {"AROME": "AROME 2,5 km", "ECMWF-ens": "ECMWF (tendance)", "ECMWF": "ECMWF (tendance)"};
const ETAT = {degage: "dégagé", mer: "au-dessus des nuages", incertain: "incertain", nuage: "dans le nuage"};
const TOUCH = window.matchMedia("(hover: none)").matches;
let G, D, state = {day: 0, cat: "rando", h: 2}, rects = [], markers = [], map;

const fmt = (x, d = 1) => x === null || x === undefined ? "—" : Number(x).toFixed(d).replace(".", ",");
function color(s) {
  if (s === null || s === undefined) return "#999";
  const stops = [[0,[179,38,30]],[30,[224,108,60]],[50,[240,165,0]],[70,[124,179,66]],[100,[31,157,85]]];
  for (let k = 1; k < stops.length; k++) {
    const [a, ca] = stops[k-1], [b, cb] = stops[k];
    if (s <= b) { const t = (s - a) / (b - a);
      return `rgb(${ca.map((v, i) => Math.round(v + t * (cb[i] - v))).join(",")})`; }
  }
  return "rgb(31,157,85)";
}
const labelOf = s => s === null ? "—" : s >= 75 ? "Top" : s >= 55 ? "Bien" : s >= 35 ? "Moyen" : "À éviter";

// Lectures : mêmes échelles que côté calcul (AMS, Beaufort, Douglas, SPC), fournies dans grid.json
const scale = (name, x) => (G.echelles[name].find(r => x < r[0]) || G.echelles[name].slice(-1)[0]);
const lPluie = x => x === null ? "" : ` → ${scale("pluie", x)[1]} (AMS)`;
const lVent = x => { if (x === null) return ""; const r = scale("beaufort", x); return ` → force ${r[1]}, ${r[2]} (Beaufort)`; };
const lMer = x => { if (x === null) return ""; const r = scale("douglas", x); return ` → mer ${r[2]} (Douglas ${r[1]})`; };
const lPer = p => p === null ? "" : ` → ${scale("periode", p)[1]}`;
const Q = a => a ? ` <a class="q" href="apprendre.html#${a}" title="Comment lire ce chiffre">?</a>` : "";
const CONF_COL = {"élevée": "#1f9d55", "moyenne": "#f0a500", "faible": "#b3261e"};
function detailScore(i) {
  const day = G.days[state.day], p = day.pens[state.cat][state.h][i], sc = day.score[state.cat][state.h][i];
  if (sc === null) return "";
  if (!p) return `<br><span class="muted">Score = 100, aucune pénalité.</span>${Q("score")}`;
  const parts = Object.entries(p).map(([k, v]) => `${G.pen_labels[k]} −${v}`).join(" − ");
  return `<br><span class="muted">Score = 100 − ${parts} = ${sc}</span>${Q("score")}`;
}

function cellText(i) {
  const day = G.days[state.day], h = state.h, c = G.cells[i];
  const sc = day.score[state.cat][h][i], R = k => day.raw[k][h][i];
  const src = day.src[h];
  let t = `<b>${CATS[state.cat].label} : ${sc === null ? "—" : sc}/100</b> · ${day.hours[h]}h · ${SRC[src] || "pas de donnée"}<br>`;
  const rain = `Pluie : ${fmt(R("pluie"))} mm/h${lPluie(R("pluie"))}${Q("pluie")}` +
    (R("proba") !== null ? ` · risque d'averse ${R("proba")} % (part des scénarios ≥ 0,5 mm/h)${Q("proba")}` : "");
  const alt = c.alt !== null ? `${c.alt} m` : "inconnu";
  const haut = R("haut_nuages") === 9999 ? "pas de plafond net" : (R("haut_nuages") !== null ? `~${R("haut_nuages")} m` : "—");
  const layer = R("base_nuages") !== null ? `<br>Couche nuageuse d'alizé : base ~${R("base_nuages")} m, haut ${haut}${Q("couche")}` : "";
  const cloud = R("etat") ? `Relief moyen de la case : ${alt} — à cette hauteur : ${ETAT[R("etat")] || R("etat")}` +
    (R("nuage_case") !== null ? ` (nuage ${R("nuage_case")} %, humidité ${R("hum_case")} %)` : "") + Q("sommet") + layer : "";
  const sea = [`Vagues : ${fmt(R("vagues"))} m${lMer(R("vagues"))}${Q("mer")}`,
               `Houle : ${fmt(R("houle"))} m · ${fmt(R("periode"), 0)} s · de ${R("dir_houle") || "—"}${lPer(R("periode"))}${Q("houle")}`,
               `Vent : ${fmt(R("vent"), 0)} km/h (${R("vent") === null ? "—" : Math.round(R("vent") / 1.852)} nœuds)${lVent(R("vent"))} · rafales ${fmt(R("rafales"), 0)} km/h${Q("vent")}`, rain];
  const lines = {
    mer: sea, surf: sea, kite: [sea[2], sea[0], rain],
    rando: [rain, `Rafales : ${fmt(R("rafales"), 0)} km/h (pointes)${Q("vent")}`, `Vent : ${fmt(R("vent"), 0)} km/h${lVent(R("vent"))}`,
            `Nuages bas : ${fmt(R("nuages_bas"), 0)} %`, cloud],
    riviere: [`Pluie des 24 h avant : ${fmt(R("pluie24"))} mm (90e percentile, case ±2,5 km) → ` +
              (R("pluie24") === null ? "—" : R("pluie24") < 4 ? "eau basse probable" : R("pluie24") < 10 ? "rivière un peu grossie" :
               R("pluie24") < 25 ? "rivière grosse, prudence" : "crue possible : ne pas s'engager") + " (seuils de l'outil 4 / 10 / 25 mm)" + Q("riviere"), rain,
              `Rafales : ${fmt(R("rafales"), 0)} km/h`],
    sommet: [cloud, rain, `Nuages bas : ${fmt(R("nuages_bas"), 0)} %`, `Rafales : ${fmt(R("rafales"), 0)} km/h (pointes)${Q("vent")}`],
  }[state.cat].filter(Boolean);
  return t + lines.join("<br>") + detailScore(i) + `<br><span class="muted">${c.ile || "En mer"} · case ${fmt(c.lat, 3)}, ${fmt(c.lon, 3)}` +
    ` (${c.kind === "mer" ? "5,5 km, modèle de vagues" : "maille AROME 2,5 km"})</span>`;
}

function spotText(sp) {
  const r = D.days[state.day].scores[sp.id] || {};
  const pill = r.score === null || r.score === undefined ? "" :
    `<span class="pill" style="background:${color(r.score)}">${r.label} · ${r.score}</span>`;
  return `<b>${sp.nom}</b> ${pill}<br><span class="muted">${sp.ile} · ${sp.secteur}</span><br>` +
    (r.start ? `Départ ${r.start} → retour vers ${r.end} · <span class="muted">${SRC[r.source] || r.source || ""}</span><br>` : "") +
    (r.reasons ? r.reasons.join(" · ") + "<br>" : "") +
    (sp.conseil ? `<span class="muted">${sp.conseil}</span><br>` : "") +
    (sp.acces ? `<span class="warn">⚠ ${sp.acces}</span><br>` : "") +
    (r.lecture && r.lecture.length ? `<b>Chiffres et lecture</b><ul class="small">${r.lecture.map(x =>
      typeof x === "string" ? `<li>${x}</li>` : `<li>${x.t}${Q(x.aide)}</li>`).join("")}</ul>` : "") +
    (r.detail ? `<b>Calcul</b>${Q("score")}<br><span class="small">Créneau = 0,6 × moyenne (${r.detail.moyenne}) + 0,4 × pire heure ` +
      `(${r.detail.pire_h}h : ${r.detail.pire}) = ${r.detail.creneau}` +
      r.detail.ajustements.map(a => `<br>${a.raison} ${a.points === null ? "→ 0" : a.points}`).join("") +
      `<br>Pénalités moyennes : ${Object.entries(r.detail.pens_moy).map(([k, v]) => k + " −" + v).join(", ") || "aucune"}` +
      `<br>Score final : <b>${r.detail.final}</b></span>` : "");
}

function draw() {
  const day = G.days[state.day];
  rects.forEach((r, i) => {
    const s = day.score[state.cat][state.h][i], src = day.src[state.h];
    r.setStyle({fillColor: color(s), fillOpacity: s === null ? 0 : (src === "AROME" ? 0.55 : 0.25),
                opacity: s === null ? 0 : 0.5});
    const el = r.getElement && r.getElement(); if (el) el.style.pointerEvents = s === null ? "none" : "auto";
  });
  markers.forEach(({m, sp}) => {
    const show = sp.cat === state.cat;
    if (show && !map.hasLayer(m)) m.addTo(map);
    if (!show && map.hasLayer(m)) map.removeLayer(m);
    const r = D.days[state.day].scores[sp.id] || {};
    m.setStyle({fillColor: color(r.score), color: "#fff"});
  });
  document.getElementById("hlabel").textContent = `${day.hours[state.h]}h`;
  const src = day.src[state.h];
  document.getElementById("hsrc").textContent = SRC[src] || "pas de donnée";
  document.getElementById("legend-txt").textContent = CATS[state.cat].legend;
  document.querySelectorAll("#days .chip").forEach((b, i) => b.classList.toggle("on", i === state.day));
  document.querySelectorAll("#cats .chip").forEach(b => b.classList.toggle("on", b.dataset.cat === state.cat));
  panel();
}

function panel() {
  const dd = D.days[state.day], sit = dd.situation || {};
  const list = D.spots.filter(s => s.cat === state.cat)
    .map(s => ({s, r: dd.scores[s.id] || {}}))
    .sort((a, b) => (b.r.score ?? -1) - (a.r.score ?? -1));
  let h = "";
  (D.warnings || []).forEach(w => h += `<p class="bad">${w}</p>`);
  const av = dd.avis || {}, cf = av.confiance || {};
  h += `<div class="card avis"><div class="row"><h3>L'avis du jour · ${dd.title.split(" · ")[0]}</h3>` +
    (cf.niveau ? `<span class="conf" style="background:${CONF_COL[cf.niveau]}">Confiance ${cf.niveau}</span>` : "") + `</div>`;
  if ((av.chiffres || []).length) {
    h += `<table class="kv">` + av.chiffres.map(c => `<tr><td>${c.label}</td><td><b>${c.valeur}</b><br>` +
      `<span class="muted">→ ${c.lecture}</span>${Q(c.aide)}</td></tr>`).join("") + `</table>`;
  }
  const lect = av.lecture || sit.texte || [];
  if (lect.length) {
    h += `<p class="small"><b>Ce qu'en lirait un prévisionniste</b> <span class="muted">(${(av.source || sit.source) === "AROME" ? "profils AROME" : "ECMWF, sans profil fin"}, 6h-16h)</span>${Q("alize")}</p><ul class="small">`;
    lect.forEach(t => h += `<li>${t}</li>`); h += "</ul>";
  }
  if ((av.retenir || []).length) h += `<p class="small"><b>À retenir :</b> ${av.retenir.join(" · ")}</p>`;
  if ((av.soleil || []).length) h += `<p class="small"><b>Sommets :</b> ${av.soleil.join(" · ")}${Q("sommet")}</p>`;
  if ((cf.lignes || []).length) h += `<details><summary class="small">Pourquoi cette confiance ?</summary><ul class="small">` +
    cf.lignes.map(x => `<li>${x.t}${Q(x.aide)}</li>`).join("") + `</ul></details>`;
  h += `<p class="small muted">Prévision : ${dd.couverture}</p></div>`;
  h += `<div class="card"><h3>${CATS[state.cat].label} — classement du jour</h3>`;
  list.forEach(({s, r}, k) => {
    h += `<div class="item" data-id="${s.id}"><div class="row"><span>${k + 1}. ${s.nom}</span>` +
      (r.score !== null && r.score !== undefined ? `<span class="pill" style="background:${color(r.score)}">${r.label} · ${r.score}</span>` : "") +
      `</div><div class="small muted">${r.start ? "Départ " + r.start + " → " + r.end + " · " : ""}${(r.reasons || []).join(" · ")}</div></div>`;
  });
  h += "</div>";
  if (D.pepites && D.pepites.length) {
    h += `<div class="card"><h3>Les pépites (levers et couchers dégagés)</h3><ul class="small">`;
    D.pepites.forEach(p => h += `<li><b>${p.jour}</b> · ${p.texte} <span class="tag ${p.fiable ? "ok" : ""}">${p.fiable ? "AROME" : "tendance, peu fiable"}</span></li>`);
    h += "</ul></div>";
  }
  if ((D.webcams || []).length) {
    h += `<div class="card"><details><summary>Webcams (${D.webcams.length}) — aussi sur la carte 📷</summary>`;
    D.webcams.forEach(w => h += `<p class="small"><b>${w.titre}</b> · <a href="${w.lien}">ouvrir sur Windy</a></p>
      <iframe class="cam" loading="lazy" src="${w.player}"></iframe>`);
    h += `</details></div>`;
  }
  h += `<p class="small muted">Cases = mailles réelles du modèle AROME (2,5 km). Pâles = heures sans AROME (ECMWF, tendance).
    Score 0-100 calculé comme pour les activités. Chaque chiffre expliqué dans <a href="apprendre.html">Apprendre à lire</a>.</p>`;
  const el = document.getElementById("panel"); el.innerHTML = h;
  el.querySelectorAll(".item").forEach(it => it.onclick = () => {
    const mk = markers.find(x => x.sp.id === it.dataset.id);
    if (mk) { map.setView(mk.m.getLatLng(), 13); mk.m.openPopup(); window.scrollTo({top: 0, behavior: "smooth"}); }
  });
}

Promise.all([fetch("grid.json", {cache: "no-store"}).then(r => r.json()),
             fetch("data.json", {cache: "no-store"}).then(r => r.json())]).then(([g, d]) => {
  G = g; D = d;
  document.getElementById("meta").textContent = `Rapport du ${d.generated} · sources`;
  document.getElementById("sources").textContent = d.sources;
  map = L.map("map", {zoomControl: true}).setView([16.15, -61.42], 10);
  L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {maxZoom: 16,
    attribution: '© OpenStreetMap, SRTM · style © OpenTopoMap (CC-BY-SA)'}).addTo(map);
  g.cells.forEach((c, i) => {
    const half = (c.size || g.step || 0.025) / 2;
    const r = L.rectangle([[c.lat - half, c.lon - half], [c.lat + half, c.lon + half]],
      {weight: 0.4, color: "#ffffff", opacity: 0.5, fillOpacity: 0.5}).addTo(map);
    r.on("click", e => L.popup({maxWidth: 300}).setLatLng(e.latlng).setContent(cellText(i)).openOn(map));
    rects.push(r);
  });
  d.spots.forEach(sp => {
    const m = L.circleMarker([sp.lat, sp.lon], {radius: 8, weight: 2, color: "#fff", fillOpacity: 1});
    m.bindPopup(() => spotText(sp), {maxWidth: 320, maxHeight: 380});
    markers.push({m, sp});
  });
  (d.webcams || []).filter(w => w.lat && w.lon).forEach(w => {
    const icon = L.divIcon({html: "📷", className: "camicon", iconSize: [22, 22]});
    L.marker([w.lat, w.lon], {icon}).addTo(map).bindPopup(
      `<b>${w.titre}</b><br><iframe class="cam" style="width:260px;height:170px" loading="lazy" src="${w.player}"></iframe>` +
      `<br><a href="${w.lien}">ouvrir sur Windy</a>`, {maxWidth: 280});
  });
  const days = document.getElementById("days");
  d.days.forEach((dd, i) => { const b = document.createElement("button"); b.className = "chip";
    b.textContent = dd.title.split(" · ")[0] + " · " + dd.title.split(" · ")[1].split(" ").slice(0, 2).join(" ");
    b.onclick = () => { state.day = i; draw(); }; days.appendChild(b); });
  const cats = document.getElementById("cats");
  Object.entries(CATS).forEach(([k, v]) => { const b = document.createElement("button"); b.className = "chip";
    b.dataset.cat = k; b.textContent = v.label; b.onclick = () => { state.cat = k; draw(); }; cats.appendChild(b); });
  // heure de départ : maintenant si c'est aujourd'hui, sinon 7h
  const nowH = new Date(new Date().toLocaleString("en-US", {timeZone: "America/Guadeloupe"})).getHours();
  const todayISO = new Date().toLocaleDateString("en-CA", {timeZone: "America/Guadeloupe"});
  const h0 = (g.days[0].date === todayISO) ? Math.min(19, Math.max(5, nowH)) : 7;
  state.h = g.days[0].hours.indexOf(h0);
  const slider = document.getElementById("hour");
  slider.max = g.days[0].hours.length - 1; slider.value = state.h;
  slider.oninput = () => { state.h = +slider.value; draw(); };
  draw();
}).catch(e => { document.getElementById("meta").textContent = "Données indisponibles : " + e; });
</script>
</body></html>
"""
