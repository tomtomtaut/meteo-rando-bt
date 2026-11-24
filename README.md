# Où sortir en Basse-Terre

Deux fois par jour (vers 5h30 et 18h, heure de Guadeloupe), ce dépôt publie une page qui dit quelles activités de la
Basse-Terre (randos, sommets, remontées de rivière) sont les plus praticables sur 3 jours, avec l'heure de départ
conseillée, l'état des sommets heure par heure, les fenêtres lever/coucher de soleil et une lecture de la situation
(force de l'alizé, couche nuageuse, air sec, poussières sahariennes). Le détail des méthodes et de leurs limites est
en bas de la page.

## Sources
- **AROME Outre-Mer Antilles** (Météo-France, open data, maille 2,5 km) : surface, profils verticaux, et le run
  précédent pour la pluie (ensemble décalé). Voisinage 3x3 mailles autour de chaque point.
- **ECMWF** via Open-Meteo : au-delà de l'échéance AROME, avec l'ensemble à 51 scénarios pour la pluie.
- **CAMS** (Copernicus) via Open-Meteo : poussières sahariennes.

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
