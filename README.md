# Où sortir en Guadeloupe

Deux fois par jour (vers 5h30 et 18h, heure de Guadeloupe), ce dépôt publie une carte et une liste qui disent quelles
activités de la Guadeloupe et de ses îles (randos, sommets, rivières, mer calme, surf, kite/wing) sont les plus
praticables sur 3 jours, avec l'heure de départ
conseillée, l'état des sommets heure par heure, les fenêtres lever/coucher de soleil et une lecture de la situation
(force de l'alizé, couche nuageuse, air sec, poussières sahariennes). Le détail des méthodes et de leurs limites est
en bas de la page.

## Sources
- **AROME Outre-Mer Antilles** (Météo-France, open data, maille 2,5 km) : surface, profils verticaux, et le run
  précédent pour la pluie (ensemble décalé). Voisinage 3x3 mailles autour de chaque point.
- **ECMWF** via Open-Meteo : au-delà de l'échéance AROME, avec l'ensemble à 51 scénarios pour la pluie.
- **CAMS** (Copernicus) via Open-Meteo : poussières sahariennes.
- **Open-Meteo Marine** : vagues et houle (hauteur, période, direction) pour la mer calme, le surf et le kite/wing.
- **Windy Webcams** (clé dans le secret `WINDY_WEBCAMS_KEY`) : toutes les webcams de l'archipel.

## Fichiers
- `spots.json` : les activités, leurs points (objectif et amont pour les rivières), durée, type. Coordonnées approximatives : à corriger librement.
- `meteo/scoring.py` : tous les seuils en haut du fichier (pluie, nuage au sommet, rafales, crues).
- `run.py` : calcule tout et écrit le site : `index.html` (l'app : Le point, Carte, Activités, Comprendre), `data.json`, `grid.json`, `debug.json`, plus le manifeste et le service worker (app installable, dernier rapport gardé hors ligne).
- `meteo/app.py` : l'app (une seule page). `meteo/avis.py` : l'avis du jour. `meteo/apprendre.py` : le contenu de « Comprendre ». `static/` : icônes.
- `history/` : les scores de chaque soir, pour comparer avec ce qu'on a vécu sur le terrain.

## Lancer à la main
Onglet **Actions** → « Rapport météo rando » → **Run workflow**. Ou en local :

```
pip install -r requirements.txt
python run.py --out site
```
