# Où sortir en Basse-Terre

Chaque soir vers 18h (heure de Guadeloupe), ce dépôt publie une page qui dit quelles activités de la Basse-Terre
(randos, sommets, remontées de rivière) sont les plus praticables les 3 jours suivants, avec l'heure de départ conseillée.

## Sources
- **AROME Outre-Mer Antilles** (Météo-France, open data, maille 2,5 km) : demain et après-demain jusqu'à ~14h.
- **ECMWF** via Open-Meteo : le reste (jour 3 = tendance) et la pluie des 2 jours passés.

## Fichiers
- `spots.json` : les activités, leurs points (objectif et amont pour les rivières), durée, type. Coordonnées approximatives : à corriger librement.
- `meteo/scoring.py` : tous les seuils en haut du fichier (pluie, nuage au sommet, rafales, crues).
- `run.py` : lance tout et écrit `site/index.html`, `site/data.json`, `site/debug.json`.
- `history/` : les scores de chaque soir, pour comparer avec ce qu'on a vécu sur le terrain.

## Lancer à la main
Onglet **Actions** → « Rapport météo rando » → **Run workflow**. Ou en local :

```
pip install -r requirements.txt
python run.py --out site
```
