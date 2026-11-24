"""Page « Apprendre à lire » : chaque chiffre affiché, comment le lire, d'où vient la règle, et les pièges.

Les tableaux sont produits à partir des mêmes constantes que le calcul (lecture.py, scoring.py, mer.py) :
la page ne peut pas dire autre chose que ce que fait l'outil.
"""

from __future__ import annotations

import math
from html import escape

from . import lecture, mer, scoring

SRC = {
    "ams": ("American Meteorological Society, Glossary of Meteorology : intensité de la pluie",
            "https://glossary.ametsoc.org/w/index.php?curid=4721"),
    "beaufort": ("Royal Meteorological Society : échelle de Beaufort (vent moyen sur 10 min, pas les rafales)",
                 "https://www.rmets.org/metmatters/beaufort-scale"),
    "douglas": ("Météo Consult / Le Figaro Nautisme : l'échelle de Douglas",
                "https://figaronautisme.meteoconsult.fr/actus-meteo-marine/2026-08-04/91081-l-echelle-de-douglas-le-langage-universel-de-l-etat-de-la-mer"),
    "spc": ("NOAA Storm Prediction Center : CAPE et descripteurs d'instabilité",
            "https://origin-east-www-spc.woc.noaa.gov/misc/tables/capetext.htm"),
    "cape_saison": ("NWS Lincoln : la portée d'une valeur de CAPE dépend de la saison",
                    "https://www.weather.gov/media/ilx/SevereWeather2023.pdf"),
    "inversion": ("AMS Glossary : inversion des alizés", "https://glossary.ametsoc.org/wiki/Trade_inversion"),
    "lcl": ("Université de Colombie-Britannique : estimer la base des cumulus (125 m par °C)",
            "https://eoas.ubc.ca/courses/atsc113/flying/met_concepts/01-met_concepts/01d-ceilings/zlcl.html"),
    "domex": ("Smith et al. 2012, Orographic Precipitation in the Tropics: The Dominica Experiment (BAMS)",
              "https://www.atmos.albany.edu/facstaff/jminder/research/smith_etal_BAMS_2012.pdf"),
    "domex2": ("Watson, Smith & Nugent : pluie orographique et vitesse de l'alizé en Dominique",
               "https://home.chpc.utah.edu/~u0559900/romps.pdf"),
    "voisinage": ("Schwartz & Sobash 2017 : probabilités par voisinage pour les modèles à maille fine (MWR)",
                  "https://impacts.ucar.edu/en/publications/generating-probabilistic-forecasts-from-convection-allowing-ensem/"),
    "ensemble": ("ECMWF, guide de l'utilisateur : ensemble et incertitude", "https://confluence.ecmwf.int/x/mENNH"),
    "arome": ("Météo-France : le modèle AROME Outre-Mer", "https://donneespubliques.meteofrance.fr/client/document/docaromeom_225.pdf"),
    "charte": ("Charte de la randonnée en Guadeloupe : conseils aux randonneurs (crues)",
               "https://www.guadeloupe-parcnational.fr/sites/guadeloupe-parcnational.fr/files/atoms/files/charte_randonnee_971_volet_gd_public.pdf"),
    "png": ("Parc national de la Guadeloupe : état des traces et signes de crue",
            "https://www.guadeloupe-parcnational.fr/sites/guadeloupe-parcnational.fr/files/atoms/files/2019-01-23_etat-traces.pdf"),
    "surf": ("Wikipédia : prévision du surf (houle de vent et houle lointaine)", "https://en.wikipedia.org/wiki/Surf_forecasting"),
    "periode": ("Mpora : périodes de houle ~10 s (houle de vent) et ~13 s et plus (groundswell)", "https://mpora.com/?p=120862"),
}


def _src(*keys) -> str:
    return "<p class='src'>Source : " + " · ".join(
        f'<a href="{escape(SRC[k][1])}">{escape(SRC[k][0])}</a>' for k in keys) + "</p>"


OUTIL = '<span class="b outil">règle de l\'outil</span>'
ECHELLE = '<span class="b ech">échelle reconnue</span>'


def _rng(table, unit, fmt=lambda x: f"{x:g}".replace(".", ",")):
    """[(limite, valeur)] → lignes « de a à b unité »."""
    out, lo = [], None
    for lim, v in table:
        if lo is None:
            out.append((f"moins de {fmt(lim)} {unit}", v))
        elif lim == math.inf:
            out.append((f"{fmt(lo)} {unit} et plus", v))
        else:
            out.append((f"{fmt(lo)} à {fmt(lim)} {unit}", v))
        lo = lim
    return out


def _table(head, rows) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{tr}</table>"


def _sec(anchor, title, badge, body) -> str:
    return f'<section id="{anchor}"><h2>{escape(title)} {badge}</h2>{body}</section>'


def page() -> str:
    pluie = _table(["Intensité", "Lecture"], _rng([(l, n) for l, n in lecture.PLUIE], "mm/h"))
    beau = _table(["Force", "Vent moyen", "Nom"], [(f, r, n) for (r, _), (_, f, n) in
                  zip(_rng([(l, f) for l, f, _ in lecture.BEAUFORT], "km/h"), lecture.BEAUFORT)])
    doug = _table(["Degré", "Creux", "Mer"], [(f, r, n) for (r, _), (_, f, n) in
                  zip(_rng([(l, f) for l, f, _ in lecture.DOUGLAS], "m"), lecture.DOUGLAS)])
    cape = _table(["CAPE", "Lecture SPC"], _rng(lecture.CAPE, "J/kg"))
    per = _table(["Période", "Lecture"], _rng(lecture.PERIODE, "s"))
    pen_pluie = _table(["Pluie retenue", "Points retirés à l'heure"], _rng(scoring.RAIN_PENALTY, "mm/h"))
    calme = _table(["Creux", "Points retirés"], _rng(mer.WAVE_CALM, "m"))
    vcalme = _table(["Vent", "Points retirés"], _rng(mer.WIND_CALM, "km/h"))
    kite = _table(["Vent moyen", "Points retirés"], _rng(mer.WIND_KITE, "km/h"))
    houle = _table(["Houle", "Points retirés"], _rng(mer.SWELL_SURF, "m"))
    pert = _table(["Période", "Points retirés"], _rng(mer.PERIOD_SURF, "s"))

    s = []
    s.append(_sec("lire", "Lire un chiffre en trois questions", "", """
      <ol>
        <li><b>Quelle valeur ?</b> Toujours avec son unité et la période qu'elle couvre (une heure, le créneau,
          la journée de 6h à 18h).</li>
        <li><b>Qu'est-ce qu'elle veut dire sur le terrain ?</b> On la place sur une échelle. Deux cas, toujours
          signalés : <span class="b ech">échelle reconnue</span> (définie par un organisme météo ou une étude publiée)
          ou <span class="b outil">règle de l'outil</span> (seuil de départ choisi ici, à caler avec tes sorties).</li>
        <li><b>Jusqu'où y croire ?</b> Quel modèle a produit le chiffre (AROME 2,5 km ou ECMWF), et est-ce que les
          modèles, les runs successifs et les scénarios sont d'accord. C'est la ligne « Confiance » de l'avis du jour.</li>
      </ol>"""))

    s.append(_sec("score", "Le score de 0 à 100", OUTIL, f"""
      <p>Chaque heure part de 100, et on retire des points pour ce qui gêne l'activité : pluie (p), nuage sur le
      parcours (n), rafales (r), orage possible (o), chaleur (c), et en mer : état de la mer (m), vent (v), taille (h),
      période (t) et orientation (d) de la houle, rafales irrégulières (k).</p>
      <p>Le score d'un créneau = 0,6 × la moyenne des heures + 0,4 × l'heure la plus mauvaise. Une seule heure très
      mauvaise pèse donc lourd : c'est voulu, une averse d'une heure en rivière suffit à gâcher la sortie.
      Ensuite viennent les ajustements rivière (pluie en amont).</p>
      <p>Étiquettes : <b>Top</b> 75 et plus · <b>Bien</b> 55-74 · <b>Moyen</b> 35-54 · <b>À éviter</b> moins de 35 ·
      <b>Non</b> = conditions jugées dangereuses (rivière).</p>
      {pen_pluie}
      <p class="small">Autres pénalités à terre : nuage sur un sommet 25 (incertain 10) · rafales sur un sommet
      15 dès 50 km/h et 35 dès 65 km/h · ailleurs 20 dès 70 km/h · orage possible 15 · chaleur 10 dès
      {scoring.HOT - 1} °C et 20 dès {scoring.HOT + 1} °C sur les sentiers exposés.</p>
      <p class="piege"><b>Pièges.</b> Un score haut ne dit rien de l'état du sentier, d'une fermeture ou d'un arrêté
      (Soufrière, Chutes Moreau…). Deux scores proches (68 et 72) ne sont pas vraiment différents : regarde plutôt
      les chiffres et la confiance.</p>"""))

    s.append(_sec("pluie", "La pluie (mm/h et mm sur le créneau)", ECHELLE, f"""
      <p>1 mm de pluie = 1 litre d'eau par m². La valeur affichée pour « 10h » est la pluie tombée de 10h à 11h.</p>
      {pluie}
      {_src("ams")}
      <p><b>Comment la valeur est choisie</b> {OUTIL}. Un modèle à maille de 2,5 km place une averse tropicale à
      quelques kilomètres près. On lit donc les 9 mailles autour du point, pour le dernier run AROME et le précédent
      (jusqu'à 18 scénarios), et on garde le 70e percentile : une valeur que 70 % des scénarios ne dépassent pas.
      En amont des rivières, on prend le 90e percentile, par prudence. Au-delà d'AROME : les 51 scénarios de
      l'ensemble ECMWF.</p>
      {_src("voisinage")}
      <p class="piege"><b>Pièges.</b> Sous les tropiques, la pluie tombe en averses courtes et fortes : « 0,4 mm/h »
      sur une heure peut être 5 minutes de grosse averse puis du sec. Et 0 mm prévu n'exclut pas un grain isolé
      qui passe entre les mailles.</p>"""))

    s.append(_sec("proba", "Le « risque d'averse » (%)", OUTIL, """
      <p>C'est la part des scénarios (voisinage × runs AROME, ou membres de l'ensemble ECMWF) qui donnent au moins
      0,5 mm/h. 30 % = 3 scénarios sur 10 prévoient une averse au moins une heure du créneau, quelque part à moins de
      2,5 km.</p>
      <p class="piege"><b>Piège.</b> Ce pourcentage est brut : il n'a pas encore été comparé à ce qui est vraiment
      tombé. Un « 30 % » ici n'est pas forcément un vrai 30 % ; c'est le but de la future comparaison avec tes sorties.</p>"""))

    s.append(_sec("riviere", "Rivières : la pluie des 24 h en amont", OUTIL, f"""
      <p>Une rivière monte avec la pluie tombée sur son bassin, en amont, parfois loin de là où tu es et sans qu'il
      pleuve sur toi. On cumule donc la pluie sur les points en amont de chaque sortie pendant les 24 h avant le
      départ, et pendant la sortie.</p>
      {_table(["Pluie en amont sur 24 h", "Lecture", "Effet sur le score"],
              [(f"moins de {scoring.RIVER_MEH_24H} mm", "eau basse et claire probable", "aucun"),
               (f"{scoring.RIVER_MEH_24H} à {scoring.RIVER_BAD_24H} mm", "un peu grossie, eau possiblement trouble", "−15"),
               (f"{scoring.RIVER_BAD_24H} à {scoring.RIVER_NOGO_24H} mm", "grosse, gués difficiles", "−35"),
               (f"{scoring.RIVER_NOGO_24H} mm et plus", "crue possible", "Non")])}
      <p>Pendant la sortie : {scoring.RIVER_NOGO_RATE} mm/h en amont, ou {scoring.RIVER_NOGO_WINDOW} mm cumulés,
      donnent « Non » (risque de montée des eaux).</p>
      <p>Ces seuils ne viennent d'aucune source officielle : aucune n'en donne pour les rivières de Guadeloupe. Ce
      qui est documenté, ce sont les signes sur place, rappelés par la charte de la randonnée et le Parc national :
      eau qui devient boueuse, feuilles et débris qui flottent = crue qui arrive. Dans ce cas on ne traverse pas,
      on monte sur un point haut et on attend la décrue. La charte conseille aussi de ne pas partir après 15h.</p>
      {_src("charte", "png")}
      <p class="piege"><b>Piège.</b> Les crues subites arrivent par temps sec sur place, avec une averse sur les
      hauteurs. Le chiffre aide à choisir le jour ; sur place, ce sont tes yeux qui décident.</p>"""))

    s.append(_sec("alize", "L'alizé vers 1 000 m", ECHELLE, """
      <p>L'alizé est le vent d'est qui souffle presque en permanence sur les Antilles. On le lit vers 1 000 m, en mer
      à l'est de l'île, avant qu'il soit dévié par le relief. Sa force décide du type de journée sur la Basse-Terre.</p>
      <ul>
        <li><b>Faible (moins de 18 km/h, soit 5 m/s)</b> : en Dominique, la campagne de mesures DOMEX a montré que
          la convection devient alors surtout thermique (chaleur) et que la pluie sur l'île baisse nettement.
          Nuages qui montent sur le massif en journée.</li>
        <li><b>Modéré</b> : régime classique, nuages accrochés côté au vent et sur les sommets.</li>
        <li><b>Fort (36 km/h et plus)</b> <span class="b outil">seuil de l'outil</span> : l'air est forcé à monter
          sur le relief, averses répétées côté au vent et sur les crêtes, abri côté sous-le-vent.</li>
      </ul>
      """ + _src("domex", "domex2") + """
      <p class="piege"><b>Piège.</b> La Dominique et la Basse-Terre se ressemblent (îles volcaniques étroites dans
      l'alizé), mais les mesures DOMEX ont été faites en Dominique, au printemps. C'est la meilleure référence
      disponible, pas une mesure en Guadeloupe.</p>"""))

    s.append(_sec("couche", "La couche nuageuse d'alizé : base et haut", ECHELLE, f"""
      <p>Dans l'alizé, l'air humide reste coincé sous une couche d'air chaud et sec qui descend d'en haut :
      l'<b>inversion des alizés</b>. Dessous, les cumulus ; dessus, le ciel clair. Sa base va d'environ 500 m à l'est
      des océans à environ 2 000 m dans l'ouest de la ceinture des alizés, où se trouvent les Antilles.</p>
      <ul>
        <li><b>Base</b> : niveau où l'air qui monte devient saturé. Estimation classique : 125 m par degré d'écart
          entre la température et le point de rosée (formule d'Espy). Ex. : 26 °C et 20 °C de rosée → 6 × 125 = 750 m.</li>
        <li><b>Haut</b> : là où l'humidité passe sous 75 % dans le profil du modèle, en mer à l'est
          <span class="b outil">seuil de l'outil</span>.</li>
        <li><b>Sur le relief</b> : entre la base − 50 m et le haut − 100 m, le relief au vent est dans le nuage ;
          à ±100 m du haut, incertain ; au-dessus, au-dessus des nuages ; sous la base, dégagé
          <span class="b outil">marges choisies (dont tes 100 m)</span>.</li>
      </ul>
      {_src("inversion", "lcl")}
      <p class="piege"><b>Pièges.</b> Dans l'ouest de la ceinture des alizés (chez nous), l'inversion n'est pas
      présente en permanence : elle apparaît selon les situations et peut manquer, par exemple au passage d'une onde
      tropicale. L'outil l'affiche alors comme « pas de plafond net ». Les niveaux du modèle sont espacés de 250 à 500 m : le « haut » est précis à
      ~200 m près, pas au mètre. Et le relief du modèle est lissé : à 2,5 km de maille, la Soufrière y est plus basse
      que les vrais 1 467 m. D'où l'idée de lire la couche en mer puis de la poser sur l'altitude réelle.</p>"""))

    s.append(_sec("sommet", "État d'un sommet, lever et coucher", OUTIL, """
      <p>Les cases colorées des sommets, heure par heure : <b>dégagé</b> (sous la base des nuages ou ciel clair),
      <b>au-dessus des nuages</b> (sommet plus haut que la couche : mer de nuages en dessous), <b>incertain</b> (à
      ±100 m du haut de la couche), <b>dans le nuage</b>. Si le profil AROME à l'altitude réelle montre déjà du nuage,
      il prime sur l'estimation de la couche.</p>
      <p>Dans les pépites, « dégagé » veut dire ciel clair autour du sommet, vue jusqu'à la côte ; « au-dessus des
      nuages » veut dire que le sommet dépasse la couche : mer de nuages sous toi, vue sur les autres sommets et îles,
      mais pas sur la côte.</p>
      <p>Lever et coucher sont calculés pour l'altitude du sommet (le soleil s'y lève un peu plus tôt). L'horizon est
      jugé sur les nuages bas et moyens en mer : à l'est au lever, à l'ouest au coucher.</p>
      <p><b>Heure de départ d'une pépite</b> <span class="b outil">méthode de l'outil</span> : on part de la durée
      aller-retour de la fiche officielle du Parc national (randoguadeloupe.gp), et on la partage entre montée et
      descente dans la proportion de la norme DIN 33466 des clubs alpins (300 m de montée par heure, 500 m de
      descente, 4 km à plat). Départ = heure du lever ou du coucher − temps de montée. Si tu as tes propres temps,
      on peut les mettre à la place dans spots.json (« montee_min »).</p>
      <p class="piege"><b>Piège.</b> Au-delà d'AROME (cases pâles), l'état est une tendance grossière.</p>"""))

    s.append(_sec("vent", "Vent et rafales (km/h, nœuds)", ECHELLE, f"""
      <p>Vent moyen à 10 m du sol, moyenné sur 10 minutes. 1 nœud = 1,852 km/h.</p>
      {beau}
      {_src("beaufort")}
      <p><b>Rafales</b> : pointes de quelques secondes. L'échelle de Beaufort ne s'applique qu'au vent moyen : quand
      l'outil écrit « rafales 41 km/h → serait force 6 », c'est un ordre de grandeur, pas un vent continu de force 6.
      Seuils de gêne sur les crêtes <span class="b outil">règle de l'outil</span> : 50 km/h (gênant), 65 km/h
      (dangereux sur une arête).</p>"""))

    s.append(_sec("cape", "L'instabilité (CAPE, J/kg)", ECHELLE, f"""
      <p>La CAPE mesure l'énergie qu'une bulle d'air qui monte peut gagner : plus elle est grande, plus un nuage
      d'averse peut grossir vite et devenir orageux.</p>
      {cape}
      {_src("spc", "cape_saison")}
      <p class="piege"><b>Piège.</b> Ces seuils ont été faits pour les orages des États-Unis, et le National Weather
      Service rappelle que la portée d'une valeur dépend de la saison et du lieu. Sous les tropiques, l'air est
      souvent instable sans orage : l'outil ne signale « orage possible » que si la CAPE dépasse
      {scoring.CAPE_UNSTABLE} J/kg <b>et</b> qu'une averse est prévue <span class="b outil">règle de l'outil</span>.</p>"""))

    s.append(_sec("mer", "L'état de la mer (creux, échelle de Douglas)", ECHELLE, f"""
      <p>Le « creux » affiché est la <b>hauteur significative</b> : la moyenne du tiers des vagues les plus hautes.</p>
      {doug}
      {_src("douglas")}
      <p><b>Mer calme</b> (kayak, snorkeling, plongée) <span class="b outil">règle de l'outil</span> :</p>
      {calme}{vcalme}
      <p class="piege"><b>Pièges.</b> Des vagues isolées peuvent être nettement plus hautes que le creux affiché.
      Et les cases font 5,5 km : une baie abritée (côte sous-le-vent, lagons) est plus calme que la case au large.</p>"""))

    s.append(_sec("houle", "La houle : hauteur, période, direction", ECHELLE, f"""
      <p>La <b>période</b> (secondes entre deux crêtes) dit d'où vient la houle. Courte = levée par le vent local,
      vagues désordonnées. Longue = née loin, dans une tempête, vagues rangées et bien plus puissantes à hauteur égale.</p>
      {per}
      {_src("surf", "periode")}
      <p><b>Surf</b> <span class="b outil">règle de l'outil</span> : la houle doit aussi venir du bon côté pour le spot
      (−40 sinon).</p>
      {houle}{pert}
      <p class="piege"><b>Piège.</b> Certains beach breaks marchent mieux avec 9-13 s et ferment avec une houle
      très longue : la période idéale dépend du spot.</p>"""))

    s.append(_sec("kite", "Kite et wingfoil", OUTIL, f"""
      <p>Vent moyen à 10 m, plus une pénalité si les rafales dépassent le vent moyen de plus de 20 km/h (vent haché).</p>
      {kite}"""))

    s.append(_sec("chaleur", "La chaleur", OUTIL, f"""
      <p>Température à 2 m, à l'ombre. Sur un sentier exposé ou en littoral, au soleil, le ressenti est bien plus
      chaud. Pénalité dès {scoring.HOT - 1} °C : partir tôt et prévoir beaucoup d'eau.</p>"""))

    s.append(_sec("poussieres", "Les poussières sahariennes", OUTIL, """
      <p>Concentration de poussières désertiques près du sol (modèle CAMS de Copernicus), en µg/m³. Au-delà de
      ~50 µg/m³ <span class="b outil">seuil de l'outil</span>, ciel laiteux et vue lointaine voilée, même avec un
      sommet au-dessus des nuages. L'air sec qui accompagne ces épisodes limite souvent les averses.</p>"""))

    s.append(_sec("everesting", "Everesting à la Soufrière", OUTIL, """
      <p>Parcours : Bains Jaunes → Pas du Roy → Savane à Mulets → Chemin des Dames → sommet, et retour. 510 m de
      dénivelé par aller-retour d'après la fiche officielle, donc 18 allers-retours pour 8 848 m.</p>
      <p>L'outil teste toutes les fenêtres de 24 h sur environ 6 jours (départ à chaque heure), sur trois points du
      parcours (Bains Jaunes, Savane à Mulets, sommet), et garde par jour la moins mauvaise. Ordre de priorité :
      pas d'orage possible (le sommet est exposé et on y passe 18 fois), puis le moins de pluie cumulée, puis le moins
      d'heures de pluie modérée (≥ 2,5 mm/h, échelle AMS : sentiers glissants), puis les rafales au sommet.</p>
      <p>⭐ s'allume si : pas d'orage, 5 mm au plus sur 24 h, aucune heure de pluie modérée, rafales au sommet sous
      50 km/h, et au moins 70 % des 51 scénarios ECMWF à 5 mm ou moins. Seuils de départ, à ajuster après une tentative.</p>
      <p class="piege"><b>Pièges.</b> À 3 jours, seul ECMWF (maille ~25 km) couvre la fenêtre : il voit le régime
      (alizé, air sec ou humide), pas le détail sur le volcan, et il sous-estime souvent la pluie de relief. La
      colonne « Modèle » dit d'où vient la fenêtre : la veille, AROME doit confirmer. La température au sommet est
      à 2 m, à l'abri du vent : avec le vent et l'humidité, le ressenti est plus froid.</p>"""))

    s.append(_sec("modeles", "D'où viennent les chiffres : les modèles", ECHELLE, """
      <ul>
        <li><b>AROME Outre-Mer Antilles</b> (Météo-France) : maille de 2,5 km, le seul qui voit les vallées et les
          crêtes de la Basse-Terre. Il va jusqu'à ~48 h. Il n'a pas sa propre analyse des observations : il part de
          l'état du modèle global ECMWF (IFS), qu'il affine.</li>
        <li><b>ECMWF</b> (via Open-Meteo) : maille 9 à 25 km, l'île y est une bosse. Bon pour la tendance de la
          journée (régime d'alizé, humidité), pas pour savoir quelle vallée prend l'averse.</li>
        <li><b>Ensemble ECMWF</b> : 51 versions du même modèle, lancées avec de petites différences. Il sert à mesurer
          l'incertitude.</li>
        <li><b>Vagues</b> : Open-Meteo Marine (modèles de vagues Météo-France et ECMWF), cases de 5,5 km.</li>
      </ul>
      """ + _src("arome") + """
      <p class="piege"><b>Piège.</b> Comme AROME part de l'état du modèle global, quand ECMWF se trompe au départ
      (onde tropicale mal placée), AROME se trompe souvent avec lui : deux modèles d'accord ne sont pas deux avis
      totalement indépendants.</p>"""))

    s.append(_sec("confiance", "La confiance", ECHELLE, """
      <p>Trois vérifications, sur la pluie des activités de Basse-Terre de 6h à 18h, classée en sec (moins de 1 mm),
      quelques averses (1-5), pluvieux (5-15), très pluvieux (15 et plus) <span class="b outil">classes de l'outil</span> :</p>
      <ul>
        <li><b>AROME contre ECMWF</b> : même classe = d'accord ; classes voisines = proches ; deux classes d'écart ou
          plus = en désaccord.</li>
        <li><b>Dernier run AROME contre le précédent</b> : une prévision qui ne bouge pas d'un calcul à l'autre est
          plus solide qu'une prévision qui change.</li>
        <li><b>Ensemble ECMWF</b> : part des 51 scénarios qui donnent 5 mm ou plus. Presque tous d'un côté (moins de
          10 % ou plus de 90 %) = scénarios groupés, situation prévisible ; entre 30 et 70 % = scénarios partagés,
          vraie incertitude.</li>
      </ul>
      <p>Confiance <b>élevée</b> si tout concorde ; <b>moyenne</b> si un écart d'une classe ou des scénarios plutôt
      groupés ; <b>faible</b> en cas de désaccord ou de scénarios partagés <span class="b outil">règle de l'outil</span>.
      L'idée de fond vient de l'ECMWF : quand les scénarios perturbés restent proches du scénario de référence,
      l'atmosphère est dans un état prévisible.</p>
      """ + _src("ensemble") + """
      <p class="piege"><b>Pièges.</b> ECMWF sous-estime souvent la pluie sur le relief (l'île y est trop basse) : un
      écart d'intensité entre AROME et ECMWF est normal ; c'est un désaccord sec / pluvieux qui compte. Et une
      confiance « élevée » reste une prévision : un grain isolé peut passer.</p>"""))

    nav = " · ".join(f'<a href="#{a}">{t}</a>' for a, t in [
        ("score", "score"), ("pluie", "pluie"), ("proba", "risque d'averse"), ("riviere", "rivières"),
        ("alize", "alizé"), ("couche", "couche nuageuse"), ("sommet", "sommets"), ("vent", "vent"),
        ("cape", "CAPE"), ("mer", "mer"), ("houle", "houle"), ("kite", "kite"), ("chaleur", "chaleur"),
        ("poussieres", "poussières"), ("everesting", "Everesting"), ("modeles", "modèles"), ("confiance", "confiance")])

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Apprendre à lire — Où sortir en Guadeloupe</title>
<style>
  :root {{ --bg:#f6f5f1; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --acc:#1f6f4a; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --fg:#ecebe6; --muted:#9c9b95; --card:#1f1f1d; --acc:#5cc492; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.5 -apple-system, system-ui, sans-serif; background:var(--bg); color:var(--fg); }}
  main {{ max-width:760px; margin:0 auto; padding:16px; }}
  h1 {{ font-size:1.5rem; margin:.2em 0; }}
  h2 {{ font-size:1.1rem; margin:0 0 .4em; }}
  section {{ background:var(--card); border-radius:12px; padding:12px 16px; margin:14px 0;
    box-shadow:0 1px 3px rgba(0,0,0,.08); scroll-margin-top:12px; }}
  section:target {{ outline:2px solid var(--acc); }}
  table {{ border-collapse:collapse; width:100%; font-size:.88rem; margin:.5em 0; }}
  td, th {{ padding:4px 6px; border-bottom:1px solid rgba(128,128,128,.2); text-align:left; }}
  .b {{ font-size:.7rem; font-weight:600; border-radius:6px; padding:1px 6px; vertical-align:2px; white-space:nowrap; }}
  .b.ech {{ background:#1f6f4a; color:#fff; }} .b.outil {{ background:#f0a500; color:#1d1d1b; }}
  .src {{ font-size:.8rem; color:var(--muted); }} .src a {{ color:inherit; }}
  .piege {{ font-size:.9rem; background:rgba(240,165,0,.12); border-radius:8px; padding:6px 10px; }}
  .small {{ font-size:.85rem; }} .nav a {{ color:inherit; }} .toc {{ font-size:.85rem; line-height:1.9; }}
  .toc a {{ color:var(--acc); }}
</style></head>
<body><main>
  <p class="nav"><a href="index.html">Carte</a> · <a href="liste.html">Liste</a> · <b>Apprendre à lire</b></p>
  <h1>Apprendre à lire les conditions</h1>
  <p class="toc">{nav}</p>
  {''.join(s)}
</main></body></html>
"""
