"""Rapport du soir : quelles activités de Basse-Terre faire dans les 3 prochains jours,
et quand voir les sommets dégagés (lever, journée, coucher).

Usage : python run.py --out site [--history history]
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meteo import arome, ecmwf, render, scoring, sommets

log = logging.getLogger("rapport")
ROOT = Path(__file__).parent


class Points:
    """Liste dédupliquée des points où on lit la météo."""

    def __init__(self):
        self.coords, self.alts, self._idx = [], [], {}

    def add(self, p: dict) -> int:
        key = (round(p["lat"], 4), round(p["lon"], 4))
        if key not in self._idx:
            self._idx[key] = len(self.coords)
            self.coords.append(key)
            self.alts.append(p.get("alt", 0))
        return self._idx[key]


def load_config():
    cfg = json.loads((ROOT / "spots.json").read_text(encoding="utf-8"))
    pts = Points()
    for spot in cfg["spots"]:
        spot["_obj"], spot["_all"], spot["_obj_high"] = [], [], []
        spot["_high"] = spot["type"] == "sommet" or (
            spot["type"] == "itinerance" and max(p["alt"] for p in spot["points"]) >= 900)
        for p in spot["points"]:
            i = pts.add(p)
            spot["_all"].append(i)
            if p["role"] == "objectif":
                spot["_obj"].append(i)
                if spot["_high"] and p["alt"] >= 700:
                    spot["_obj_high"].append(i)
    for s in cfg.get("sommets", []):
        s["_i"] = pts.add(s)
    hz = cfg.get("horizons", {})
    idx_h = {k: pts.add(v) for k, v in hz.items() if isinstance(v, dict)}
    return cfg, pts, idx_h


def high_points(cfg, pts) -> dict[int, float]:
    """Points d'altitude (≥ 700 m) dont on calcule l'état : sommets + objectifs des sorties en altitude."""
    out = {s["_i"]: s["alt"] for s in cfg.get("sommets", [])}
    for spot in cfg["spots"]:
        for p in spot["points"]:
            i = pts.add(p)
            if i in spot["_obj_high"]:
                out[i] = p["alt"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--history", default=None, help="dossier où archiver les scores du jour")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    now = datetime.now(timezone.utc)
    cfg, pts, idx_h = load_config()
    n = len(pts.coords)
    warnings, debug = [], {"points": [{"lat": la, "lon": lo, "alt": a} for (la, lo), a in zip(pts.coords, pts.alts)]}

    ec = ecmwf.fetch(pts.coords, pts.alts)
    if ec is None:
        warnings.append("ECMWF (Open-Meteo) indisponible ce soir : le jour 3 n'est pas calculé.")

    ar, profiles, run_txt = None, {}, "AROME indisponible"
    try:
        found = arome.find_run(now)
        if found:
            run, hmax = found
            results, inventory, grid = arome.download(run, hmax, pts.coords)
            ar = arome.to_series(run, hmax, results, inventory, n)
            end_local = (run + timedelta(hours=hmax)).astimezone(scoring.TZ)
            run_txt = (f"AROME Antilles run {run:%d/%m %Hh} UTC (jusqu'à {render.fdate(end_local.date())} "
                       f"{end_local.hour}h)")
            debug.update({"run": run.isoformat(), "hmax": hmax, "keys": ar["keys"], "precip_mode": ar.get("precip_mode"),
                          "inventory": inventory, "grid": grid, "files_read": len(results)})
            missing = [k for k in ("precip", "lcc", "rh", "gust") if k not in ar]
            if missing:
                warnings.append(f"Champs AROME non trouvés : {', '.join(missing)} (remplacés par ECMWF).")

            # Profils verticaux, seulement aux heures de jour (lever → coucher)
            hours = [h for h in range(0, hmax + 1)
                     if sommets.FIRST_H - 1 <= (run + timedelta(hours=h)).astimezone(scoring.TZ).hour <= sommets.LAST_H]
            try:
                res_p, inv_p, _ = arome.download(run, hmax, pts.coords, paquets=arome.PAQUETS_PROFIL, hours=hours)
                pr = arome.to_profiles(run, res_p, inv_p, hours, n)
                profiles = pr["profiles"]
                debug.update({"inventory_profil": inv_p, "profil_niveaux": pr["used"], "profil_heures": len(profiles)})
                if not profiles:
                    warnings.append("Profils verticaux AROME non lus : état des sommets estimé depuis la surface.")
            except Exception as e:  # noqa: BLE001
                log.exception("Profils AROME en échec")
                warnings.append(f"Profils verticaux AROME en échec ({e.__class__.__name__}).")
        else:
            warnings.append("Aucun run AROME récent publié : prévision ECMWF seule, moins précise sur le relief.")
    except Exception as e:  # noqa: BLE001 — le rapport doit sortir même sans AROME
        log.exception("AROME en échec")
        warnings.append(f"AROME en échec ({e.__class__.__name__}) : prévision ECMWF seule.")

    sources = run_txt + (f" · {ec['model']} via Open-Meteo au-delà" if ec else "")
    merged = scoring.merge(ar, ec, n)
    merged.summit_state = sommets.compute_states(high_points(cfg, pts), profiles, merged, idx_h.get("au_vent"))

    today = now.astimezone(scoring.TZ).date()
    titles = ["Demain", "Après-demain", "Dans 3 jours"]
    days = []
    for k in range(1, 4):
        d = today + timedelta(days=k)
        all_ = [(s, scoring.evaluate_day(s, merged, d)) for s in cfg["spots"]]
        days.append({
            "date": d.isoformat(),
            "title": f"{titles[k - 1]} · {render.fdate(d)}",
            "short": render.fdate(d).split(" ")[0][:3] + f". {d.day}",
            "all": all_,
            "top": scoring.top3(all_),
            "sommets": [sommets.day_summary(s, s["_i"], merged.summit_state, merged, d,
                                            idx_h.get("est"), idx_h.get("ouest")) for s in cfg.get("sommets", [])],
        })
    local = now.astimezone(scoring.TZ)
    report = {
        "generated": f"{render.fdate(local.date())} à {local.hour}h{local:%M}",
        "sources": sources, "warnings": warnings, "days": days, "spots": cfg["spots"],
        "exclus": cfg.get("exclus", []), "webcams": cfg.get("webcams", []),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render.page(report), encoding="utf-8")
    compact = {
        "generated_utc": now.isoformat(), "sources": sources, "warnings": warnings,
        "days": [{
            "date": d["date"], "top": [s["id"] for s, _ in d["top"]],
            "scores": {s["id"]: {k: r.get(k) for k in ("score", "label", "start", "end", "source", "reasons")}
                       for s, r in d["all"]},
            "sommets": {x["nom"]: {"etats": {h["h"]: h["state"] for h in x["hours"]},
                                   "details": {h["h"]: h["det"] for h in x["hours"]},
                                   "lever": x["lever"], "coucher": x["coucher"], "texte": x["texte"]}
                        for x in d["sommets"]},
        } for d in days],
    }
    (out / "data.json").write_text(json.dumps(compact, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "debug.json").write_text(json.dumps(debug, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if args.history:
        h = Path(args.history)
        h.mkdir(parents=True, exist_ok=True)
        (h / f"{local:%Y-%m-%d}.json").write_text(json.dumps(compact, ensure_ascii=False, default=str), encoding="utf-8")
    for d in days:
        log.info("%s : %s", d["title"], ", ".join(f"{s['nom']} ({r['score']})" for s, r in d["top"]) or "rien")
        sf = d["sommets"][0] if d["sommets"] else None
        if sf:
            log.info("  %s : lever %s, %s", sf["nom"], sf["lever"]["etat"], sf["texte"])


if __name__ == "__main__":
    main()
