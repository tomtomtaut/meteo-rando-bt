"""L'app (une seule page) : Le point · Carte · Activités · Comprendre.

Le script Python ne produit que les données (data.json, grid.json) ; cette page les affiche.
Trois niveaux d'information : coup d'œil (étiquette, note, créneau) → fiche (chiffres clés et leur lecture)
→ « Tout le détail » (heure par heure, calcul, sources).
DATA_BASE permet de lire les données ailleurs que là où la page est hébergée (laisser vide = même dossier).
"""

from __future__ import annotations

from html import escape

from . import apprendre

DATA_BASE = ""


def page(data_base: str = DATA_BASE) -> str:
    toc, sections = apprendre.content()
    toc_html = "".join(f'<a class="chip" href="#comprendre/{a}">{escape(t)}</a>' for a, t in toc)
    return (TEMPLATE.replace("%%DATA_BASE%%", data_base)
            .replace("%%TOC%%", toc_html).replace("%%COMPRENDRE%%", sections))


MANIFEST = """{
  "name": "Où sortir en Guadeloupe",
  "short_name": "Sortir GP",
  "start_url": "./index.html#point",
  "scope": "./",
  "display": "standalone",
  "background_color": "#f6f5f1",
  "theme_color": "#1f6f4a",
  "lang": "fr",
  "icons": [
    {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "icon-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
"""

# Service worker : l'app et Leaflet en cache ; données d'abord depuis le réseau, sinon le dernier rapport gardé.
SW = """const V = "sortir-v1";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.hostname.includes("tile.opentopomap") || u.hostname.includes("windy")) return;
  const fresh = e.request.mode === "navigate" || /\\.json$/.test(u.pathname) || u.pathname.endsWith("/");
  if (fresh) {
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); return r; })
      .catch(() => caches.match(e.request, {ignoreSearch: true}).then(r => r || caches.match("./index.html"))));
  } else {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(n => { const c = n.clone(); caches.open(V).then(x => x.put(e.request, c)); return n; })));
  }
});
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f6f4a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Sortir GP">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
<title>Où sortir en Guadeloupe</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root { --bg:#f6f5f1; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:rgba(128,128,128,.22); --acc:#1f6f4a;
  --tabh:58px; --safe:env(safe-area-inset-bottom, 0px); }
@media (prefers-color-scheme: dark) { :root { --bg:#141413; --fg:#ecebe6; --muted:#9c9b95; --card:#1f1f1d; --acc:#5cc492; } }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
html, body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.45 -apple-system, system-ui, "Segoe UI", sans-serif; }
button { font:inherit; color:inherit; }
a { color:var(--acc); }
.muted { color:var(--muted); } .small { font-size:.85rem; } .xs { font-size:.75rem; }
/* En-tête : le même partout */
header.top { position:sticky; top:0; z-index:500; background:var(--bg); padding:calc(8px + env(safe-area-inset-top, 0px)) 14px 8px;
  border-bottom:1px solid var(--line); }
.hrow { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.hrow b { font-size:1.05rem; }
#age { font-size:.75rem; } #age.old { color:#b06000; font-weight:600; }
.seg { display:flex; gap:4px; margin-top:8px; background:var(--card); border-radius:12px; padding:3px; border:1px solid var(--line); }
.seg button { flex:1; border:0; background:none; padding:6px 2px; border-radius:9px; font-size:.82rem; line-height:1.15; cursor:pointer; }
.seg button small { display:block; font-size:.7rem; color:var(--muted); }
.seg button.on { background:var(--acc); color:#fff; } .seg button.on small { color:rgba(255,255,255,.85); }
/* Contenu */
main { max-width:720px; margin:0 auto; padding:10px 12px calc(var(--tabh) + var(--safe) + 24px); }
.card { background:var(--card); border-radius:14px; padding:12px 14px; margin:10px 0; box-shadow:0 1px 2px rgba(0,0,0,.06); }
.card h2 { font-size:1rem; margin:0; }
.ch { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.more { border:0; background:none; color:var(--acc); padding:6px 0 0; font-size:.85rem; cursor:pointer; }
.chips { display:flex; gap:6px; overflow-x:auto; padding:2px 0 6px; scrollbar-width:none; }
.chips::-webkit-scrollbar { display:none; }
.chip { flex:none; border:1px solid var(--line); background:var(--card); color:var(--fg); border-radius:999px; padding:6px 12px;
  font-size:.85rem; white-space:nowrap; cursor:pointer; text-decoration:none; }
.chip.on { background:var(--acc); border-color:var(--acc); color:#fff; }
/* Note : une seule forme partout */
.badge { display:inline-flex; align-items:center; justify-content:center; min-width:44px; height:28px; padding:0 8px; border-radius:8px;
  color:#fff; font-weight:700; font-size:.9rem; flex:none; }
.badge.sm { min-width:30px; height:22px; font-size:.75rem; border-radius:6px; padding:0 5px; }
.lab { font-size:.72rem; font-weight:600; }
/* Lignes d'activité */
.row { display:flex; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--line); cursor:pointer; }
.row:last-child { border-bottom:0; }
.row .t { flex:1; min-width:0; }
.row .n { font-weight:600; font-size:.93rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.row .s { font-size:.78rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.row .cmp { display:flex; gap:3px; }
.kv { display:grid; grid-template-columns:1fr 1fr; gap:10px 14px; margin:10px 0 0; }
.kv div { min-width:0; } .kv .k { font-size:.72rem; color:var(--muted); } .kv .v { font-size:.9rem; font-weight:600; line-height:1.25; }
ul.l { margin:6px 0; padding-left:1.1em; font-size:.86rem; } ul.l li { margin:.3em 0; }
.q { display:inline-block; width:1.2em; height:1.2em; line-height:1.15em; text-align:center; border-radius:50%; border:1px solid currentColor;
  color:var(--acc); font-size:.7rem; font-weight:700; text-decoration:none; margin-left:4px; vertical-align:1px; }
.warn { color:#b06000; font-size:.85rem; } .bad { color:#b3261e; font-size:.85rem; }
.tag { font-size:.68rem; border:1px solid currentColor; border-radius:6px; padding:0 4px; color:var(--muted); white-space:nowrap; }
.conf { color:#fff; border-radius:999px; padding:2px 9px; font-size:.75rem; font-weight:600; white-space:nowrap; }
/* Barres horaires */
.strip { display:flex; gap:2px; margin:6px 0 2px; }
.strip span { flex:1; height:22px; border-radius:4px; color:#fff; font-size:.62rem; font-weight:600; display:flex; align-items:center;
  justify-content:center; cursor:pointer; text-shadow:0 0 2px rgba(0,0,0,.45); }
.strip span.sel { outline:2px solid var(--fg); } .strip span.faded { opacity:.45; }
.why { font-size:.82rem; background:rgba(128,128,128,.08); border-radius:10px; padding:6px 10px; margin-top:6px; }
.why ul { margin:4px 0; padding-left:1.1em; }
/* Tableau heure par heure */
.tw { overflow-x:auto; } table.hh { border-collapse:collapse; font-size:.75rem; margin:6px 0; }
table.hh td, table.hh th { padding:4px 6px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
/* Barre d'onglets : la même partout, en bas */
nav.tabs { position:fixed; left:0; right:0; bottom:0; z-index:900; display:flex; background:var(--card); border-top:1px solid var(--line);
  padding-bottom:var(--safe); }
nav.tabs a { flex:1; height:var(--tabh); display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px;
  text-decoration:none; color:var(--muted); font-size:.7rem; }
nav.tabs a svg { width:22px; height:22px; stroke:currentColor; fill:none; stroke-width:1.8; }
nav.tabs a.on { color:var(--acc); font-weight:600; }
/* Carte */
#mapwrap { position:fixed; left:0; right:0; bottom:calc(var(--tabh) + var(--safe)); top:var(--top, 110px); display:none; }
#mapwrap.on { display:block; }
#map { position:absolute; inset:0; }
.mapctl { position:absolute; left:8px; right:8px; z-index:600; }
.mapctl.t { top:8px; } .mapctl.b { bottom:10px; background:var(--card); border-radius:12px; padding:6px 10px; box-shadow:0 1px 4px rgba(0,0,0,.2); }
.mapctl .chips { padding:0; }
.hour { display:flex; align-items:center; gap:10px; } .hour input { flex:1; accent-color:var(--acc); }
.grad { height:6px; border-radius:3px; margin-top:4px; background:linear-gradient(90deg,#b3261e,#e06c3c 30%,#f0a500 50%,#7cb342 70%,#1f9d55); }
.camicon { font-size:18px; line-height:22px; text-align:center; background:none; border:0; }
/* Fiche (monte du bas) */
#sheet { position:fixed; inset:0; z-index:1000; display:none; }
#sheet.on { display:block; }
#sheet .bg { position:absolute; inset:0; background:rgba(0,0,0,.35); }
#sheet .pane { position:absolute; left:0; right:0; bottom:0; max-height:88vh; overflow-y:auto; background:var(--bg); border-radius:18px 18px 0 0;
  padding:8px 14px calc(20px + var(--safe)); max-width:720px; margin:0 auto; }
#sheet .grip { width:40px; height:4px; border-radius:2px; background:var(--line); margin:4px auto 8px; }
#sheet .x { position:absolute; right:10px; top:8px; border:0; background:var(--card); border-radius:50%; width:32px; height:32px; font-size:1.1rem; cursor:pointer; }
#sheet h2 { font-size:1.1rem; margin:4px 40px 4px 0; }
/* Comprendre */
#v-comprendre section { background:var(--card); border-radius:14px; padding:12px 14px; margin:12px 0; scroll-margin-top:130px; }
#v-comprendre h2 { font-size:1.02rem; margin:0 0 .4em; }
#v-comprendre table { border-collapse:collapse; width:100%; font-size:.82rem; margin:.4em 0; }
#v-comprendre td, #v-comprendre th { padding:4px 6px; border-bottom:1px solid var(--line); text-align:left; }
.b { font-size:.66rem; font-weight:600; border-radius:6px; padding:1px 6px; vertical-align:2px; white-space:nowrap; }
.b.ech { background:#1f6f4a; color:#fff; } .b.outil { background:#f0a500; color:#1d1d1b; }
.src { font-size:.78rem; color:var(--muted); } .src a { color:inherit; }
.piege { font-size:.86rem; background:rgba(240,165,0,.12); border-radius:8px; padding:6px 10px; }
iframe.cam { width:100%; height:210px; border:0; border-radius:10px; margin-top:6px; }
.ever { display:flex; gap:8px; align-items:center; }
.ever.on { background:rgba(240,165,0,.14); border:2px solid #f0a500; }
/* Grand écran : onglets dans l'en-tête, commandes de carte groupées, fiche en panneau à droite */
#sheet { pointer-events:none; } #sheet .bg, #sheet .pane { pointer-events:auto; }
@media (min-width: 1000px) {
  header.top { padding:10px 20px; }
  .hrow { justify-content:flex-start; gap:16px; margin-right:470px; }
  .seg { max-width:480px; }
  nav.tabs { top:0; bottom:auto; left:auto; right:16px; background:none; border:0; padding:12px 0 0; gap:4px; }
  nav.tabs a { flex:none; flex-direction:row; height:38px; padding:0 14px; gap:6px; font-size:.88rem; border-radius:999px; }
  nav.tabs a svg { width:18px; height:18px; }
  nav.tabs a.on { background:rgba(31,111,74,.12); }
  main { padding-bottom:40px; }
  #mapwrap { bottom:0; }
  .mapctl.t, .mapctl.b { right:auto; width:440px; }
  #sheet .pane { left:auto; right:0; top:var(--top, 110px); bottom:0; width:440px; max-height:none; border-radius:0;
    box-shadow:-2px 0 12px rgba(0,0,0,.15); padding-bottom:20px; }
  #sheet .grip { display:none; }
  body.map #sheet .bg { display:none; }
}
</style></head>
<body>
<header class="top" id="top">
  <div class="hrow"><b>Où sortir en Guadeloupe</b><span id="age" class="muted"></span></div>
  <div class="seg" id="days"></div>
</header>
<main id="view"><p class="muted">Chargement…</p></main>
<div id="mapwrap">
  <div id="map"></div>
  <div class="mapctl t"><div class="chips" id="mapcats"></div></div>
  <div class="mapctl b">
    <div class="hour"><input type="range" id="hour" min="0" max="14" step="1"><span class="small"><b id="hlabel"></b> <span class="muted xs" id="hsrc"></span></span></div>
    <div class="grad"></div><div class="xs muted" id="legend"></div>
  </div>
</div>
<div id="sheet"><div class="bg"></div><div class="pane"><div class="grip"></div><button class="x" aria-label="Fermer">×</button><div id="sheet-body"></div></div></div>
<nav class="tabs">
  <a href="#point" data-t="point"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/></svg>Le point</a>
  <a href="#carte" data-t="carte"><svg viewBox="0 0 24 24"><path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15M15 6v15"/></svg>Carte</a>
  <a href="#activites" data-t="activites"><svg viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>Activités</a>
  <a href="#comprendre" data-t="comprendre"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.5"/></svg>Comprendre</a>
</nav>
<template id="t-comprendre"><div class="chips" style="flex-wrap:wrap">%%TOC%%</div>%%COMPRENDRE%%</template>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";
const BASE = "%%DATA_BASE%%";
const CATS = {rando: "Randos", riviere: "Rivières", sommet: "Sommets", mer: "Mer calme", surf: "Surf", kite: "Kite / wing"};
const LEG = {rando: "pluie, rafales, chaleur, orages", riviere: "pluie des 24 h avant + pluie à l'heure", sommet: "comme rando + nuage au sommet",
  mer: "petite mer, peu de vent", surf: "hauteur et période de houle", kite: "vent établi 22-45 km/h"};
const SRC = {"AROME": "AROME 2,5 km", "ECMWF-ens": "ECMWF (tendance)", "ECMWF": "ECMWF (tendance)", "mixte": "AROME + ECMWF"};
const DIRS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
let D = null, G = null, map = null, rects = [], markers = [], SP = {};
const S = Object.assign({day: 0, cat: "all", ile: "all", cmp: false, h: null, avoid: false}, (() => {
  try { return JSON.parse(localStorage.getItem("sortir") || "{}"); } catch (e) { return {}; } })());
const save = () => { try { localStorage.setItem("sortir", JSON.stringify({cat: S.cat, ile: S.ile, cmp: S.cmp})); } catch (e) {} };

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const n = (x, d = 0) => x === null || x === undefined || Number.isNaN(x) ? "—" : Number(x).toFixed(d).replace(".", ",");
const Q = a => a ? `<a class="q" href="#comprendre/${a}" aria-label="Comment lire">?</a>` : "";
const dirName = d => d === null || d === undefined ? "—" : DIRS[Math.floor(((d % 360) + 22.5) / 45) % 8];
function color(s) {
  if (s === null || s === undefined) return "#999";
  const st = [[0, [179, 38, 30]], [30, [224, 108, 60]], [50, [240, 165, 0]], [70, [124, 179, 66]], [100, [31, 157, 85]]];
  for (let k = 1; k < st.length; k++) { const [a, ca] = st[k - 1], [b, cb] = st[k];
    if (s <= b) { const t = (s - a) / (b - a); return `rgb(${ca.map((v, i) => Math.round(v + t * (cb[i] - v))).join(",")})`; } }
  return "rgb(31,157,85)";
}
const label = s => s === null || s === undefined ? "—" : s >= 75 ? "Top" : s >= 55 ? "Bien" : s >= 35 ? "Moyen" : "À éviter";
function badge(r, sm) {
  if (!r || r.score === null || r.score === undefined) return `<span class="badge ${sm ? "sm" : ""}" style="background:#999">—</span>`;
  const no = r.label === "Non";
  return `<span class="badge ${sm ? "sm" : ""}" style="background:${no ? "#7a1f1a" : color(r.score)}" title="${esc(r.label)}">${no ? "Non" : r.score}</span>`;
}
const day = () => D.days[S.day] || D.days[0];
const sc = id => (day().scores || {})[id] || {};
const isToday = () => day().date === new Date().toLocaleDateString("en-CA", {timeZone: "America/Guadeloupe"});

/* ---------- En-tête : jour et âge du rapport ---------- */
function header() {
  const box = $("#days"); box.innerHTML = "";
  D.days.forEach((dd, i) => {
    const [a, b] = dd.title.split(" · ");
    const nm = a === "Aujourd'hui" ? "Auj." : a === "Après-demain" ? "Après-dem." : a === "Dans 3 jours" ? "J+3" : a;
    const btn = document.createElement("button"); btn.className = i === S.day ? "on" : "";
    btn.innerHTML = `${esc(nm)}<small>${esc(b.split(" ").slice(0, 2).join(" "))}</small>`;
    btn.onclick = () => { S.day = i; render(); }; box.appendChild(btn);
  });
  const h = (Date.now() - new Date(D.generated_utc).getTime()) / 36e5;
  const el = $("#age"); el.className = h > 14 ? "old" : "muted";
  el.textContent = (navigator.onLine === false ? "hors ligne · " : "") + `rapport ${D.generated.split(" à ")[1] || ""}` +
    (h >= 1 ? ` · il y a ${Math.round(h)} h` : "");
  document.documentElement.style.setProperty("--top", $("#top").offsetHeight + "px");
}

/* ---------- Le point ---------- */
function vPoint() {
  const dd = day(), av = dd.avis || {}, cf = av.confiance || {};
  let h = "";
  (D.warnings || []).slice(0, 1).forEach(w => h += `<p class="bad">${esc(w)}${D.warnings.length > 1 ? ` <span class="muted">(+${D.warnings.length - 1})</span>` : ""}</p>`);
  // Avis du jour : coup d'œil, puis lecture sur demande
  h += `<div class="card"><div class="ch"><h2>L'avis du jour</h2>` +
    (cf.niveau ? `<span class="conf" style="background:${{"élevée": "#1f9d55", "moyenne": "#f0a500", "faible": "#b3261e"}[cf.niveau]}">Confiance ${cf.niveau}</span>` : "") + `</div>`;
  const KN = {"Alizé vers 1 000 m": "Alizé (1 000 m)", "Couche nuageuse d'alizé": "Nuages d'alizé", "Mer au large": "Mer au large", "Poussières sahariennes": "Poussières"};
  h += `<div class="kv">` + (av.chiffres || []).map(c => { const k = c.label.replace(/ \(.*\)$/, "");
    const lab = KN[k] || (k.startsWith("Pluie") ? "Pluie (Basse-Terre)" : k.startsWith("Instabilité") ? "Instabilité" : k);
    return `<div><div class="k">${esc(lab)}</div><div class="v">${esc(c.valeur.replace(/ \(.*\)$/, ""))}</div></div>`; }).join("") + `</div>`;
  h += `<div id="avis-more" hidden><ul class="l">` + (av.chiffres || []).map(c => `<li><b>${esc(c.label)}</b> → ${esc(c.lecture)}${Q(c.aide)}</li>`).join("") + `</ul>`;
  if ((av.lecture || []).length) h += `<p class="small"><b>Ce qu'en lirait un prévisionniste</b>${Q("alize")}</p><ul class="l">` + av.lecture.map(t => `<li>${esc(t)}</li>`).join("") + `</ul>`;
  if ((cf.lignes || []).length) h += `<p class="small"><b>Pourquoi cette confiance</b>${Q("confiance")}</p><ul class="l">` + cf.lignes.map(x => `<li>${esc(x.t)}</li>`).join("") + `</ul>`;
  h += `<p class="xs muted">Prévision : ${esc(dd.couverture)}</p></div><button class="more" data-tog="avis-more">Lire l'analyse</button></div>`;
  // À faire : le top
  h += `<div class="card"><h2>À faire ${isToday() ? "aujourd'hui" : "ce jour-là"}</h2>`;
  (dd.top || []).forEach(id => h += rowHtml(id, true));
  if (!(dd.top || []).length) h += `<p class="small muted">Rien de vraiment praticable selon les modèles.</p>`;
  h += `<button class="more" data-go="#activites">Toutes les activités →</button></div>`;
  // Pépites du jour
  const dayname = dd.title.split(" · ")[1];
  const pep = (D.pepites || []).filter(p => p.jour === dayname), other = (D.pepites || []).filter(p => p.jour !== dayname);
  h += `<div class="card"><h2>Pépites (lever, coucher)</h2>`;
  if (pep.length) pep.forEach((p, i) => h += pepHtml(p, "p" + i));
  else h += `<p class="small muted">Pas de lever ni de coucher dégagé prévu ce jour-là.${other.length ? ` Prochaine : <b>${esc(other[0].jour)}</b> · ${esc(other[0].texte)}` : ""}</p>`;
  h += `</div>`;
  // Sommets : une ligne par sommet, la barre horaire au toucher
  h += `<div class="card"><h2>Sommets heure par heure${Q("sommet")}</h2>`;
  Object.entries(dd.sommets || {}).forEach(([nom, x], k) => {
    h += `<div class="row" data-tog="som${k}"><div class="t"><div class="n">${esc(nom)} <span class="muted xs">${x.alt || ""} m</span></div>` +
      `<div class="s">${esc(x.texte || "")}</div></div>${sunMark("🌅", x.lever)}${sunMark("🌇", x.coucher)}</div>` +
      `<div id="som${k}" hidden>${stripHtml(nom, x, k)}</div>`;
  });
  h += `</div>`;
  // Everesting
  const ev = D.everesting;
  if (ev && (ev.jours || []).length) {
    const st = ev.etoile, b = ev.meilleure;
    h += `<div class="card ever ${st ? "on" : ""}" data-tog="ev-more" style="cursor:pointer"><div class="t" style="flex:1"><b>${st ? "⭐" : "☆"} Everesting Soufrière</b><div class="small">` +
      (st ? `Départ ${esc(st.depart_txt)} · ${n(st.pluie, 1)} mm sur 24 h${st.source === "AROME" ? "" : " · tendance"}` :
        `Pas encore de fenêtre · la moins mauvaise : ${esc(b.depart_txt)}`) + `</div></div><span class="muted">›</span></div>`;
    h += `<div id="ev-more" hidden class="card">${evHtml(ev)}</div>`;
  }
  // Webcams : repliées, chargées au toucher
  if ((D.webcams || []).length) {
    h += `<div class="card"><div class="ch" data-tog="cams" style="cursor:pointer"><h2>Webcams (${D.webcams.length})</h2><span class="muted">›</span></div><div id="cams" hidden>` +
      D.webcams.map((w, i) => `<div class="row" data-cam="${i}"><div class="t"><div class="n">📷 ${esc(w.titre)}</div></div></div><div id="cam${i}"></div>`).join("") + `</div></div>`;
  }
  return h;
}
function sunMark(icon, s) {
  if (!s) return "";
  return `<span class="xs" style="white-space:nowrap">${icon}${s.top ? "<b style='color:#1f9d55'>✓</b>" : "<span class='muted'>✗</span>"}</span>`;
}
function stripHtml(nom, x, k) {
  const E = D.etats || {};
  const hs = Object.keys(x.etats || {}).map(Number).sort((a, b) => a - b);
  let s = `<div class="strip">` + hs.map(hh => { const st = x.etats[hh]; const e = E[st || "none"] || ["—", "#ccc"];
    return `<span style="background:${e[1]}" data-why="${k}:${hh}">${hh}</span>`; }).join("") + `</div>`;
  s += `<div class="xs muted">` + Object.entries(E).filter(([key]) => key !== "none").map(([, e]) => `<span style="color:${e[1]}">■</span> ${esc(e[0])}`).join(" · ") + `</div>`;
  s += `<div class="small">🌅 ${esc(x.lever.heure)} : ${esc((E[x.lever.etat || "none"] || ["—"])[0].toLowerCase())} · 🌇 ${esc(x.coucher.heure)} : ${esc((E[x.coucher.etat || "none"] || ["—"])[0].toLowerCase())}</div>`;
  return s + `<div class="why" id="why${k}" hidden></div>`;
}
function pepHtml(p, key) {
  let h = `<div class="row" data-tog="${key}"><div class="t"><div class="n" style="white-space:normal">${esc(p.texte)}</div>` +
    `<div class="s">${p.fiable ? "AROME" : "tendance ECMWF, peu fiable"}${p.confiance ? " · confiance " + esc(p.confiance) : ""}</div></div><span class="muted">›</span></div><div id="${key}" hidden>`;
  (p.details || []).forEach(x => {
    h += `<p class="small"><b>${esc(x.nom)}</b> (${x.alt} m) · ${esc(x.creneau || "")}${x.source ? ` <a href="${esc(x.source)}" target="_blank" rel="noopener">fiche</a>` : ""}</p>` +
      `<ul class="l">${(x.lignes || []).map(l => `<li>${esc(l)}</li>`).join("")}</ul>` + (x.horizon ? `<p class="small">${esc(x.horizon)}</p>` : "");
  });
  return h + `<p class="xs muted">${esc(((p.details || [])[0] || {}).rappel || "")}${Q("couche")}</p></div>`;
}
function evHtml(ev) {
  let h = `<p class="small">${ev.allers_retours} allers-retours Bains Jaunes ↔ sommet (${ev.dplus_ar} m chacun). Meilleure fenêtre de 24 h par jour de départ.${Q("everesting")}</p>`;
  ev.jours.forEach(w => {
    h += `<div class="row" style="cursor:default"><div class="t"><div class="n">${w.etoile ? "⭐ " : ""}${esc(w.depart_txt)}</div>` +
      `<div class="s" style="white-space:normal">${n(w.pluie, 1)} mm · ${w.heures_moderees} h ≥ 2,5 mm/h · orage ${w.orage ? "oui" : "non"} · rafales ${n(w.rafales)} km/h · nuit ${n(w.tmin)} °C · nuage ${w.nuage_h} h · ` +
      `${w.scenarios === null ? "—" : w.scenarios + " % des scénarios secs"} · ${esc(w.source)}</div></div></div>`;
  });
  return h + `<p class="xs muted">⭐ : pas d'orage, ≤ ${ev.seuils.pluie} mm sur 24 h, aucune heure ≥ 2,5 mm/h, rafales &lt; ${ev.seuils.rafales} km/h, ≥ ${ev.seuils.scenarios} % des scénarios secs (seuils de l'outil). Au-delà de ~2 jours : tendance, à confirmer la veille.</p>`;
}

/* ---------- Activités : une seule liste ---------- */
function rowHtml(id, single) {
  const sp = SP[id], r = sc(id);
  if (!sp) return "";
  const when = r.start ? `${r.start} → ${r.end}${r.passe ? " (passé)" : ""}` : "";
  const why = (r.reasons || [])[0] || "";
  let right = badge(r);
  const cmp = S.cmp && !single;
  if (cmp) right = `<span class="cmp">` + D.days.map(dd => badge((dd.scores || {})[id], true)).join("") + `</span>`;
  return `<div class="row" data-id="${esc(id)}">${cmp ? "" : right}<div class="t"><div class="n">${esc(sp.nom)}</div>` +
    `<div class="s">${esc([when, why, sp.ile].filter(Boolean).join(" · "))}</div></div>${cmp ? right : ""}</div>`;
}
function vActivites() {
  const iles = [...new Set(D.spots.map(s => s.ile).filter(Boolean))].sort((a, b) => (a === "Mer") - (b === "Mer") || a.localeCompare(b));
  let h = `<div class="chips" id="f-cat">` + [["all", "Toutes"], ...Object.entries(CATS)].map(([k, v]) => `<button class="chip ${S.cat === k ? "on" : ""}" data-cat="${k}">${v}</button>`).join("") + `</div>`;
  h += `<div class="chips" id="f-ile">` + [["all", "Toutes les îles"], ...iles.map(x => [x, x])].map(([k, v]) => `<button class="chip ${S.ile === k ? "on" : ""}" data-ile="${esc(k)}">${esc(v)}</button>`).join("") +
    `<button class="chip ${S.cmp ? "on" : ""}" data-cmp="1">Comparer 3 jours</button></div>`;
  const list = D.spots.filter(s => (S.cat === "all" || s.cat === S.cat) && (S.ile === "all" || s.ile === S.ile))
    .map(s => ({s, r: sc(s.id)})).sort((a, b) => (b.r.label === "Non" ? -1 : b.r.score ?? -1) - (a.r.label === "Non" ? -1 : a.r.score ?? -1));
  const good = list.filter(x => x.r.label !== "Non" && (x.r.score ?? 0) >= 35), bad = list.filter(x => !good.includes(x));
  h += `<div class="card">${good.map(x => rowHtml(x.s.id)).join("") || `<p class="small muted">Rien de recommandé avec ces filtres.</p>`}</div>`;
  if (bad.length) h += `<button class="more" data-tog="avoid">À éviter ou déconseillé (${bad.length})</button><div id="avoid" class="card" hidden>${bad.map(x => rowHtml(x.s.id)).join("")}</div>`;
  return h;
}

/* ---------- Fiche d'une activité ---------- */
function hoursTable(sp, r) {
  const hs = ((r.detail || {}).heures || []).filter(x => x.brut);
  if (!hs.length) return "";
  const pl = b => n(b.pluie, 1) + (b.proba ? ` (${b.proba} %)` : "");
  const C = {
    rando: [["Pluie mm/h", pl, "pluie"], ["Rafales", b => n(b.rafales), "vent"], ["Vent", b => n(b.vent), "vent"], ["°C", b => n(b.t2m), "chaleur"], ["Nuages bas", b => n(b.nuages_bas) + " %", "couche"]],
    riviere: [["Pluie mm/h", pl, "pluie"], ["Amont mm/h", b => n(b.amont, 1), "riviere"], ["Rafales", b => n(b.rafales), "vent"], ["°C", b => n(b.t2m), "chaleur"]],
    mer: [["Creux m", b => n(b.creux, 1), "mer"], ["Vent", b => n(b.vent), "vent"], ["Rafales", b => n(b.rafales), "vent"], ["Pluie", pl, "pluie"]],
    surf: [["Houle m", b => n(b.houle, 1), "houle"], ["Période s", b => n(b.periode), "houle"], ["Direction", b => dirName(b.dir), "houle"], ["Vent", b => n(b.vent), "vent"]],
    kite: [["Vent (nœuds)", b => n(b.vent) + (b.vent ? ` (${Math.round(b.vent / 1.852)})` : ""), "kite"], ["Rafales", b => n(b.rafales), "vent"],
      ["Écart", b => (b.rafales ?? null) !== null && (b.vent ?? null) !== null ? n(b.rafales - b.vent) : "—", "kite"], ["Pluie", pl, "pluie"]],
  };
  const E = D.etats || {};
  let c = C[sp.cat] || C.rando;
  if (sp.cat === "sommet") c = C.rando.concat([["Points hauts", b => (b.points_hauts || []).map(p => p.nom.split(" (")[0] + " : " + ((E[p.etat || "none"] || ["—"])[0]).toLowerCase()).join(", ") || "—", "sommet"]]);
  let t = `<div class="tw"><table class="hh"><tr><th>h</th><th>Note</th>` + c.map(([l, , a]) => `<th>${l}${Q(a)}</th>`).join("") + `<th>Retiré</th><th>Modèle</th></tr>`;
  hs.forEach(x => { t += `<tr><td>${x.h}h</td><td><b>${x.score}</b></td>` + c.map(([, f]) => `<td>${esc(f(x.brut))}</td>`).join("") +
    `<td>${esc(Object.entries(x.pens).map(([k, v]) => (D.pen_labels[k] || k) + " −" + v).join(", ") || "—")}</td><td class="muted">${x.brut.src === "AROME" ? "AROME" : "ECMWF"}</td></tr>`; });
  t += `</table></div><p class="xs muted">Vent et rafales en km/h.</p>`;
  if (sp.cat === "surf" && sp.houle) t += `<p class="small muted">Houle qui convient à ce spot : de ${dirName(sp.houle[0])} à ${dirName(sp.houle[1])}.</p>`;
  return t;
}
function fiche(id) {
  const sp = SP[id], r = sc(id), d = r.detail;
  if (!sp) return;
  let h = `<h2>${esc(sp.nom)}</h2><div class="ch"><div class="small muted">${esc([sp.ile, sp.secteur, CATS[sp.cat], sp.niveau].filter(Boolean).join(" · "))}</div>${badge(r)}</div>`;
  h += `<p class="small"><b>${esc(day().title)}</b>${r.start ? ` · départ ${r.start} → retour ${r.end}` : ""}${r.passe ? " <span class='tag'>créneau passé</span>" : ""} <span class="muted">· ${esc(SRC[r.source] || r.source || "")}</span></p>`;
  if ((r.reasons || []).length) h += `<p class="small">${esc(r.reasons.join(" · "))}</p>`;
  if (sp.acces) h += `<p class="warn">⚠ ${esc(sp.acces)}</p>`;
  if (sp.conseil) h += `<p class="small muted">${esc(sp.conseil)}</p>`;
  if (d && d.heures) h += `<div class="strip">` + d.heures.map(x => `<span style="background:${color(x.score)}">${x.h}</span>`).join("") + `</div><div class="xs muted">Note heure par heure sur le créneau.</div>`;
  if ((r.lecture || []).length) h += `<p class="small" style="margin-bottom:0"><b>Les chiffres et ce qu'ils veulent dire</b></p><ul class="l">` +
    r.lecture.map(x => typeof x === "string" ? `<li>${esc(x)}</li>` : `<li>${esc(x.t)}${Q(x.aide)}</li>`).join("") + `</ul>`;
  // Les autres jours, d'un coup d'œil
  h += `<div class="chips" style="margin-top:6px">` + D.days.map((dd, i) => { const o = (dd.scores || {})[id] || {};
    return `<button class="chip ${i === S.day ? "on" : ""}" data-fday="${i}" data-fid="${esc(id)}">${esc(dd.title.split(" · ")[0])} · ${o.label === "Non" ? "Non" : (o.score ?? "—")}</button>`; }).join("") + `</div>`;
  if (d) {
    h += `<button class="more" data-tog="fd">Tout le détail : heure par heure, calcul</button><div id="fd" hidden>` + hoursTable(sp, r);
    const pm = Object.entries(d.pens_moy || {}).map(([k, v]) => `${k} −${n(v, 1)}`).join(", ") || "aucune";
    h += `<p class="small"><b>Calcul de la note</b>${Q("score")}</p><ul class="l"><li>Chaque heure part de 100, moins des pénalités. Moyennes par heure : ${esc(pm)}.</li>` +
      `<li>Note du créneau = 0,6 × moyenne des heures (${d.moyenne}) + 0,4 × heure la plus mauvaise (${d.pire_h}h : ${d.pire}) = <b>${d.creneau}</b></li>` +
      (d.ajustements || []).map(a => `<li>${esc(a.raison)} ${a.points === null ? "→ note 0" : ": " + (a.points > 0 ? "+" : "") + n(a.points, 0)}</li>`).join("") +
      `<li>Note finale : <b>${d.final}</b></li></ul></div>`;
  }
  openSheet(h);
}
function openSheet(h) { $("#sheet-body").innerHTML = h; $("#sheet").classList.add("on"); $("#sheet .pane").scrollTop = 0; }
function closeSheet() { $("#sheet").classList.remove("on"); }

/* ---------- Carte ---------- */
function mapCat() { return S.cat === "all" ? "rando" : S.cat; }
function cellText(i) {
  const dd = G.days[S.day], h = S.h, c = G.cells[i], cat = mapCat();
  const s = dd.score[cat][h][i], R = k => dd.raw[k][h][i], p = (dd.pens[cat][h] || [])[i];
  const sc2 = {score: s, label: label(s)};
  let t = `<h2>${CATS[cat]} · ${dd.hours[h]}h</h2><div class="ch"><div class="small muted">${esc(c.ile || "En mer")} · case de ${c.kind === "mer" ? "5,5 km (vagues)" : "2,5 km (AROME)"}${c.alt !== null ? " · relief ~" + c.alt + " m" : ""}</div>${badge(sc2)}</div>`;
  const L = [];
  const pl = R("pluie"); L.push(`Pluie : ${n(pl, 1)} mm/h${R("proba") ? ` (risque d'averse ${R("proba")} %)` : ""}${Q("pluie")}`);
  if (cat === "riviere") L.push(`Pluie des 24 h avant (amont, 90e percentile) : ${n(R("pluie24"), 1)} mm${Q("riviere")}`);
  if (["mer", "surf", "kite"].includes(cat)) {
    L.push(`Creux : ${n(R("vagues"), 1)} m${Q("mer")}`);
    L.push(`Houle : ${n(R("houle"), 1)} m · ${n(R("periode"))} s · de ${R("dir_houle") || "—"}${Q("houle")}`);
    L.push(`Vent : ${n(R("vent"))} km/h (${R("vent") === null ? "—" : Math.round(R("vent") / 1.852)} nœuds) · rafales ${n(R("rafales"))} km/h${Q("vent")}`);
  } else {
    L.push(`Rafales : ${n(R("rafales"))} km/h · vent ${n(R("vent"))} km/h${Q("vent")}`);
    L.push(`Nuages bas : ${n(R("nuages_bas"))} %`);
    if (R("etat")) { const E = D.etats || {};
      L.push(`À l'altitude de la case : ${esc(((E[R("etat")] || [R("etat")])[0]).toLowerCase())}${R("base_nuages") !== null ? ` · couche d'alizé : base ~${R("base_nuages")} m, haut ${R("haut_nuages") === 9999 ? "sans plafond net" : "~" + R("haut_nuages") + " m"}` : ""}${Q("couche")}`); }
  }
  t += `<ul class="l">${L.map(x => `<li>${x}</li>`).join("")}</ul>`;
  t += `<p class="small muted">Note = 100${p ? " − " + Object.entries(p).map(([k, v]) => `${D.pen_labels[k] || k} ${v}`).join(" − ") : ""} = ${s ?? "—"}${Q("score")}</p>`;
  return t;
}
function initMap() {
  map = L.map("map", {zoomControl: false}).setView([16.15, -61.42], 10);
  L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {maxZoom: 16, attribution: "© OpenStreetMap, SRTM · OpenTopoMap (CC-BY-SA)"}).addTo(map);
  G.cells.forEach((c, i) => {
    const half = (c.size || G.step || 0.025) / 2;
    const r = L.rectangle([[c.lat - half, c.lon - half], [c.lat + half, c.lon + half]], {weight: .4, color: "#fff", opacity: .5, fillOpacity: .5}).addTo(map);
    r.on("click", () => openSheet(cellText(i))); rects.push(r);
  });
  D.spots.forEach(sp => { const m = L.circleMarker([sp.lat, sp.lon], {radius: 8, weight: 2, color: "#fff", fillOpacity: 1});
    m.on("click", () => fiche(sp.id)); markers.push({m, sp}); });
  (D.webcams || []).filter(w => w.lat && w.lon).forEach(w => L.marker([w.lat, w.lon], {icon: L.divIcon({html: "📷", className: "camicon", iconSize: [22, 22]})})
    .addTo(map).on("click", () => openSheet(`<h2>${esc(w.titre)}</h2><iframe class="cam" loading="lazy" src="${esc(w.player)}"></iframe><p class="small"><a href="${esc(w.lien)}" target="_blank" rel="noopener">Ouvrir sur Windy</a></p>`)));
  const sl = $("#hour"); sl.oninput = () => { S.h = +sl.value; drawMap(); };
}
function drawMap() {
  if (!G || !map) return;
  const dd = G.days[S.day], cat = mapCat();
  if (S.h === null || S.h >= dd.hours.length) {
    const nowH = new Date(new Date().toLocaleString("en-US", {timeZone: "America/Guadeloupe"})).getHours();
    const h0 = isToday() ? Math.min(19, Math.max(5, nowH)) : 7; S.h = Math.max(0, dd.hours.indexOf(h0));
  }
  const sl = $("#hour"); sl.max = dd.hours.length - 1; sl.value = S.h;
  rects.forEach((r, i) => { const s = dd.score[cat][S.h][i], src = dd.src[S.h];
    r.setStyle({fillColor: color(s), fillOpacity: s === null ? 0 : (src === "AROME" ? .55 : .25), opacity: s === null ? 0 : .5});
    const el = r.getElement && r.getElement(); if (el) el.style.pointerEvents = s === null ? "none" : "auto"; });
  markers.forEach(({m, sp}) => { const show = sp.cat === cat; if (show && !map.hasLayer(m)) m.addTo(map); if (!show && map.hasLayer(m)) map.removeLayer(m);
    m.setStyle({fillColor: color(((D.days[S.day].scores || {})[sp.id] || {}).score)}); });
  $("#hlabel").textContent = dd.hours[S.h] + "h"; $("#hsrc").textContent = SRC[dd.src[S.h]] || "pas de donnée";
  $("#legend").textContent = `0 → 100 · ${LEG[cat]} · cases pâles = tendance ECMWF`;
  $("#mapcats").innerHTML = Object.entries(CATS).map(([k, v]) => `<button class="chip ${cat === k ? "on" : ""}" data-cat="${k}">${v}</button>`).join("");
}

/* ---------- Navigation ---------- */
function tab() { return (location.hash.slice(1).split("/")[0]) || "point"; }
function render() {
  header(); closeSheet();
  const t = tab();
  document.querySelectorAll("nav.tabs a").forEach(a => a.classList.toggle("on", a.dataset.t === t));
  const isMap = t === "carte";
  $("#mapwrap").classList.toggle("on", isMap); $("#view").hidden = isMap; document.body.classList.toggle("map", isMap);
  if (isMap) {
    const go = () => { if (!map) initMap(); drawMap(); setTimeout(() => map.invalidateSize(), 50); };
    if (G) go(); else { $("#legend").textContent = "Chargement de la carte…";
      fetch(BASE + "grid.json").then(r => r.json()).then(g => { G = g; go(); }).catch(e => $("#legend").textContent = "Carte indisponible : " + e); }
    return;
  }
  const v = $("#view");
  if (t === "activites") v.innerHTML = vActivites();
  else if (t === "comprendre") {
    v.innerHTML = `<div id="v-comprendre">` + $("#t-comprendre").innerHTML + `</div>`;
    const sec = location.hash.split("/")[1]; const el = sec && document.getElementById(sec);
    if (el) setTimeout(() => el.scrollIntoView({block: "start"}), 30); else window.scrollTo(0, 0);
  } else v.innerHTML = vPoint();
}
document.addEventListener("click", e => {
  const el = e.target.closest("[data-tog],[data-id],[data-go],[data-cat],[data-ile],[data-cmp],[data-why],[data-cam],[data-fday]");
  if (!el || e.target.closest("a.q")) { if (e.target.closest("a.q")) closeSheet(); return; }
  if (el.dataset.tog) { const x = document.getElementById(el.dataset.tog); if (x) { x.hidden = !x.hidden;
      if (el.classList.contains("more") && el.dataset.tog === "avis-more") el.textContent = x.hidden ? "Lire l'analyse" : "Masquer l'analyse"; } return; }
  if (el.dataset.id) return fiche(el.dataset.id);
  if (el.dataset.go) { location.hash = el.dataset.go; return; }
  if (el.dataset.cat) { S.cat = el.dataset.cat; save(); if (tab() === "carte") drawMap(); else render(); return; }
  if (el.dataset.ile) { S.ile = el.dataset.ile; save(); render(); return; }
  if (el.dataset.cmp) { S.cmp = !S.cmp; save(); render(); return; }
  if (el.dataset.fday) { S.day = +el.dataset.fday; header(); if (tab() === "carte") drawMap(); else if (tab() !== "comprendre") $("#view").innerHTML = tab() === "activites" ? vActivites() : vPoint(); fiche(el.dataset.fid); return; }
  if (el.dataset.cam) { const i = +el.dataset.cam, box = document.getElementById("cam" + i), w = D.webcams[i];
    box.innerHTML = box.innerHTML ? "" : `<iframe class="cam" loading="lazy" src="${esc(w.player)}"></iframe><p class="xs"><a href="${esc(w.lien)}" target="_blank" rel="noopener">Ouvrir sur Windy</a></p>`; return; }
  if (el.dataset.why) { const [k, hh] = el.dataset.why.split(":"); const nom = Object.keys(day().sommets)[+k], x = day().sommets[nom];
    el.parentElement.querySelectorAll("span").forEach(s => s.classList.toggle("sel", s === el));
    const box = document.getElementById("why" + k); box.hidden = false;
    const E = D.etats || {}, st = x.etats[hh];
    box.innerHTML = `<b>${hh}h : ${esc((E[st || "none"] || ["—"])[0])}</b><ul>` + ((x.pourquoi || {})[hh] || []).map(l => `<li>${esc(l)}</li>`).join("") + `</ul>${Q("sommet")}`; }
});
$("#sheet .bg").onclick = closeSheet; $("#sheet .x").onclick = closeSheet;
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });
window.addEventListener("hashchange", render);
window.addEventListener("online", header); window.addEventListener("offline", header);

fetch(BASE + "data.json").then(r => r.json()).then(d => {
  D = d; D.spots.forEach(s => SP[s.id] = s);
  const today = new Date().toLocaleDateString("en-CA", {timeZone: "America/Guadeloupe"});
  const i = D.days.findIndex(x => x.date === today); S.day = i >= 0 ? i : 0;
  render();
}).catch(e => { $("#view").innerHTML = `<p class="bad">Données indisponibles (${esc(e)}). Sans réseau, l'app affiche le dernier rapport gardé s'il existe.</p>`; });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
</script>
</body></html>
"""
