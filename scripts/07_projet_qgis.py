"""Étape 7 (optionnelle) - Projet QGIS complet : couches, thèmes, mises en page, atlas, modèles.

À exécuter dans QGIS (console Python), après 05_livrables. Le projet
livrables/02_Donnees_SIG/diagnostic_zan_rouen.qgz contient :
  - les couches livrées, symbolisées selon la charte (chemins relatifs, sans fond de carte externe) ;
  - un thème de carte par planche ;
  - 4 mises en page A3 prêtes à imprimer et 1 atlas communal A4 (71 pages) ;
  - les 2 modèles du modeleur graphique (voir 08_modeles_traitement.py).
"""
from pathlib import Path

from qgis.core import (QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,
                       QgsSizeScaleTransformer,
                       QgsDataDefinedSizeLegend, QgsFeatureRequest, QgsFillSymbol, QgsLayoutItemLabel,
                       QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemMapOverview, QgsLayoutItemPage,
                       QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutItemShape, QgsLayoutPoint,
                       QgsLayoutSize, QgsLegendStyle, QgsMapThemeCollection, QgsMarkerSymbol,
                       QgsPalLayerSettings, QgsPrintLayout, QgsProject, QgsProperty,
                       QgsRendererCategory, QgsSingleSymbolRenderer, QgsSymbolLayer,
                       QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtGui import QColor, QFont

try:
    RACINE = Path(__file__).resolve().parents[1]
except NameError:  # exécution depuis la console QGIS
    RACINE = Path(globals().get("RACINE_PROJET", "."))
DOSSIER = RACINE / "livrables" / "02_Donnees_SIG"
GPKG = DOSSIER / "diagnostic_zan_rouen.gpkg"
AUTEUR = "Jaurès DAA-HINGBANON"
MM = QgsUnitTypes.LayoutMillimeters
BLEU = "#184f95"

ZONES = {"U": ("Zones urbaines (U)", "#b8262b"), "AU": ("Zones à urbaniser (AU)", "#eb6834"),
         "A": ("Zones agricoles (A)", "#d4a800"), "N": ("Zones naturelles (N)", "#1f6f3f")}
VOCATIONS = {"Habitat / mixte": "#e5714a", "Habitat / mixte (2AU, fermée)": "#f3b49b",
             "Activités économiques": "#7b3fa0", "Loisirs et équipements": "#d4a03a"}
DESTINATIONS = {"hab": ("Habitat", "#e5714a"), "act": ("Activité économique", "#7b3fa0"),
                "mix": ("Mixte habitat / activité", "#d4a03a"), "inf": ("Infrastructures", "#6f6f6f"),
                "inc": ("Destination inconnue", "#c3c2bb")}
EFFORT = {"Réduction d'au moins 50 %": "#184f95", "Réduction de moins de 50 %": "#5598e7",
          "Hausse jusqu'à +50 %": "#eb6834", "Hausse de plus de 50 %": "#b8262b",
          "Consommation marginale (< 1 ha en 2011-2021)": "#d9d8d2"}
FLUX = {"Artificialisation": "#b8262b", "Désartificialisation": "#159a6b"}
GISEMENTS = {"Dent creuse": "#b8262b", "Grand tènement": "#6e1414", "Division parcellaire": "#f0a04b"}


CATEGORIES_DIV = {"U habitat": ("Zone U à dominante habitat", "#e5714a"),
                  "U autre": ("Autre zone U", "#7b3fa0"),
                  "AU": ("Zone à urbaniser (AU)", "#d4a03a"),
                  "A ou N": ("Zone agricole ou naturelle", "#1f6f3f")}


# --- Couches et symbologie ---------------------------------------------------------------------
def couche(nom, titre):
    lyr = QgsVectorLayer(f"{GPKG}|layername={nom}", titre, "ogr")
    if not lyr.isValid():
        raise RuntimeError(f"couche invalide : {nom}")
    return lyr


def remplissage(couleur, contour="#ffffff", largeur=0.1, opacite=1.0, style="solid"):
    s = QgsFillSymbol.createSimple({"color": couleur, "outline_color": contour,
                                    "outline_width": str(largeur), "style": style})
    s.setOpacity(opacite)
    return s


def categories(lyr, champ, table, opacite=1.0, contour="#ffffff", largeur=0.1):
    """contour=None : contour de la couleur du remplissage (petits objets plus lisibles)."""
    cats = []
    for valeur, style in table.items():
        lib, coul = style if isinstance(style, tuple) else (valeur, style)
        sym = remplissage(coul, contour=contour or coul, largeur=largeur, opacite=opacite)
        cats.append(QgsRendererCategory(valeur, sym, lib))
    lyr.setRenderer(QgsCategorizedSymbolRenderer(champ, cats))


def etiquettes(lyr, expression, taille=8, gras=False):
    s = QgsPalLayerSettings()
    s.fieldName = expression
    s.isExpression = True
    fmt = QgsTextFormat()
    police = QFont("Segoe UI")
    police.setBold(gras)
    fmt.setFont(police)
    fmt.setSize(taille)
    tampon = QgsTextBufferSettings()
    tampon.setEnabled(True)
    tampon.setSize(1)
    tampon.setColor(QColor("white"))
    fmt.setBuffer(tampon)
    s.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def couche_cercles():
    """Cercles proportionnels (surface ∝ hectares), couleur = destination dominante.

    Méthode standard QGIS : symbole unique, taille pilotée par un transformateur « surface »
    (légende des tailles générée automatiquement) et couleur définie par expression.
    Renvoie aussi une couche « légende » des couleurs, absente des cartes.
    """
    lyr = couche("communes_centroides", "Consommation d'ENAF 2011-2021 (cercles)")
    vmax = max(f["conso_1121_ha"] for f in lyr.getFeatures())
    dmax = 16  # diamètre (mm) du plus grand cercle
    taille = QgsProperty.fromField("conso_1121_ha")
    taille.setTransformer(QgsSizeScaleTransformer(QgsSizeScaleTransformer.Area, 0, vmax, 0, dmax, 0, 0.5))
    couleur = "CASE " + " ".join(f"WHEN \"dominante_1121\" = '{k}' THEN '{c}'"
                                 for k, (_, c) in DESTINATIONS.items()) + " END"
    sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": "#e5714a", "outline_color": "#ffffff",
                                        "outline_width": "0.3"})
    sym.setOpacity(0.9)
    sym.setDataDefinedSize(taille)
    sym.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyFillColor,
                                              QgsProperty.fromExpression(couleur))
    r = QgsSingleSymbolRenderer(sym)
    legende = QgsDataDefinedSizeLegend()
    legende.setLegendType(QgsDataDefinedSizeLegend.LegendCollapsed)
    legende.setTitle("Consommation 2011-2021 (ha)")
    legende.setClasses([QgsDataDefinedSizeLegend.SizeClass(dmax * (v / vmax) ** 0.5, f"{v} ha")
                        for v in (80, 40, 10)])
    legende.setSymbol(QgsMarkerSymbol.createSimple({"name": "circle", "color": "255,255,255,0",
                                                    "outline_color": "#52514e", "outline_width": "0.25"}))
    r.setDataDefinedSizeLegend(legende)
    r.setOrderBy(QgsFeatureRequest.OrderBy([QgsFeatureRequest.OrderByClause("conso_1121_ha", False)]))
    r.setOrderByEnabled(True)  # grands cercles dessous, petits dessus
    lyr.setRenderer(r)
    etiquettes(lyr, "CASE WHEN \"conso_1121_ha\" >= 14 OR \"nom\" = 'Rouen' THEN \"nom\" || '\n' || "
                    "format_number(\"conso_1121_ha\", 0) || ' ha' END", 7.5, gras=True)

    leg_couleurs = couche("communes_centroides", "Destination dominante")
    cats = []
    for code, (lib, coul) in DESTINATIONS.items():
        m = QgsMarkerSymbol.createSimple({"name": "circle", "color": coul, "outline_color": "#ffffff",
                                          "outline_width": "0.3", "size": "3.5"})
        cats.append(QgsRendererCategory(code, m, lib))
    leg_couleurs.setRenderer(QgsCategorizedSymbolRenderer("dominante_1121", cats))
    return lyr, leg_couleurs


def couche_limites():
    lyr = couche("communes_indicateurs", "Limites communales")
    lyr.setRenderer(QgsSingleSymbolRenderer(remplissage("255,255,255,0", "#a9a79f", 0.2)))
    return lyr


def couche_masque_atlas():
    """Dans l'atlas : voile blanc sur les communes voisines, contour noir sur la commune courante."""
    lyr = couche("communes_indicateurs", "Masque atlas (communes voisines)")
    sym = remplissage("255,255,255,0", "#a9a79f", 0.2)
    sl = sym.symbolLayer(0)
    sl.setDataDefinedProperty(QgsSymbolLayer.PropertyFillColor, QgsProperty.fromExpression(
        "CASE WHEN @atlas_featureid IS NULL OR @atlas_featureid = $id THEN '255,255,255,0' "
        "ELSE '255,255,255,170' END"))
    sl.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth, QgsProperty.fromExpression(
        "CASE WHEN @atlas_featureid = $id THEN 0.8 ELSE 0.2 END"))
    sl.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeColor, QgsProperty.fromExpression(
        "CASE WHEN @atlas_featureid = $id THEN '#0b0b0b' ELSE '#a9a79f' END"))
    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
    return lyr


# --- Mises en page -----------------------------------------------------------------------------
def placer(layout, item, x, y, w=None, h=None):
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    if w is not None:
        item.attemptResize(QgsLayoutSize(w, h, MM))
    return item


def texte(layout, txt, x, y, w, h, taille=9, couleur="#0b0b0b", gras=False, html=False):
    lab = QgsLayoutItemLabel(layout)
    lab.setText(txt)
    fmt = QgsTextFormat()
    police = QFont("Segoe UI")
    police.setBold(gras)
    fmt.setFont(police)
    fmt.setSize(taille)
    fmt.setColor(QColor(couleur))
    lab.setTextFormat(fmt)
    if html:
        lab.setMode(QgsLayoutItemLabel.ModeHtml)
    return placer(layout, lab, x, y, w, h)


def rectangle(layout, x, y, w, h, couleur):
    r = QgsLayoutItemShape(layout)
    r.setShapeType(QgsLayoutItemShape.Rectangle)
    r.setSymbol(remplissage(couleur, couleur, 0, style="solid"))
    return placer(layout, r, x, y, w, h)


def carte(layout, theme, emprise, x, y, w, h):
    m = QgsLayoutItemMap(layout)
    placer(layout, m, x, y, w, h)
    m.setFollowVisibilityPreset(True)
    m.setFollowVisibilityPresetName(theme)
    m.zoomToExtent(emprise)
    m.setFrameEnabled(True)
    m.setFrameStrokeColor(QColor("#c3c2b7"))
    m.setBackgroundColor(QColor("#f1f0ec"))  # hors territoire
    return m


def legende(layout, m, couches, x, y, titre="Légende"):
    leg = QgsLayoutItemLegend(layout)
    leg.setTitle(titre)
    leg.setLinkedMap(m)
    leg.setAutoUpdateModel(False)
    racine = leg.model().rootGroup()
    racine.removeAllChildren()
    for lyr in couches:
        racine.addLayer(lyr)
    for style, taille, gras in ((QgsLegendStyle.Title, 11, True), (QgsLegendStyle.Subgroup, 9, True),
                                (QgsLegendStyle.SymbolLabel, 8.5, False)):
        police = QFont("Segoe UI")
        police.setBold(gras)
        police.setPointSizeF(taille)
        leg.setStyleFont(style, police)
    placer(layout, leg, x, y)
    leg.setResizeToContents(True)
    leg.adjustBoxSize()
    return leg


def habillage(layout, m, x_echelle, y_echelle, x_nord, y_nord, km):
    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle("Single Box")
    sb.setLinkedMap(m)
    sb.setUnits(QgsUnitTypes.DistanceKilometers)
    sb.setUnitLabel("km")
    sb.setNumberOfSegments(2)
    sb.setNumberOfSegmentsLeft(0)
    sb.setUnitsPerSegment(km / 2)
    placer(layout, sb, x_echelle, y_echelle)
    nord = QgsLayoutItemPicture(layout)
    nord.setPicturePath(":/images/north_arrows/layout_default_north_arrow.svg")
    nord.setLinkedMap(m)
    placer(layout, nord, x_nord, y_nord, 9, 13)


eau_legende = []


def planche_a3(projet, nom, titre, sous_titre, theme, emprise, couches_leg, commentaire, sources, km=10):
    lay = QgsPrintLayout(projet)
    lay.initializeDefaults()
    lay.setName(nom)
    lay.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)
    rectangle(lay, 0, 0, 420, 24, BLEU)
    texte(lay, titre, 10, 4, 300, 10, 20, "#ffffff", gras=True)
    texte(lay, sous_titre, 10, 14.5, 300, 7, 10.5, "#dce8f6")
    texte(lay, "Territoire : Métropole Rouen Normandie\nÉtude indépendante · données ouvertes",
          300, 6, 110, 14, 9.5, "#ffffff")
    m = carte(lay, theme, emprise, 10, 30, 290, 250)
    habillage(lay, m, 14, 270, 287, 34, km)
    legende(lay, m, couches_leg + [eau_legende[0]], 310, 32)
    texte(lay, commentaire, 310, 200, 100, 70, 9, "#52514e", html=True)
    texte(lay, f"Sources : {sources}", 10, 284, 300, 8, 7.5, "#52514e")
    texte(lay, f"Réalisation : {AUTEUR} · Lambert-93 (EPSG:2154)", 310, 284, 100, 8, 7.5, "#52514e")
    projet.layoutManager().addLayout(lay)
    return lay


INDICATEURS_ATLAS = """<div style="font-family:'Segoe UI';font-size:8.5pt;color:#1f1f1f;line-height:1.3">
<b style="color:#184f95">CONSOMMATION D'ENAF (CEREMA)</b><br>
2011-2021 : <b>[% format_number("conso_1121_ha", 1) %] ha</b><br>
2021-2025 : <b>[% format_number("conso_2125_ha", 1) %] ha</b><br>
Évolution du rythme : [% CASE WHEN "evol_rythme_pct" IS NULL THEN '—'
  ELSE format_number("evol_rythme_pct", 0) || ' %' END %]<br>
[% "classe_effort" %]<br><br>
<b style="color:#184f95">OCCUPATION DU SOL ET PLUi</b><br>
Part artificialisée (2022) : [% format_number("part_artif_2022_pct", 1) %] %<br>
Artificialisation nette 2019-2022 : [% format_number("artif_nette_1922_ha", 1) %] ha<br>
Zones AU : [% format_number("zone_AU_ha", 1) %] ha, dont [% format_number("au_non_artif_ha", 1) %] ha
non artificialisés<br>
Terres agricoles (RPG) en zone AU : [% format_number("au_rpg_ha", 1) %] ha
</div>"""


def atlas_a4(projet, couverture, couches_leg, emprise_metropole):
    lay = QgsPrintLayout(projet)
    lay.initializeDefaults()
    lay.setName("Atlas communal A4 (71 communes)")
    lay.pageCollection().page(0).setPageSize("A4", QgsLayoutItemPage.Landscape)
    rectangle(lay, 0, 0, 297, 18, BLEU)
    texte(lay, '[% "nom" %]', 8, 3, 180, 12, 18, "#ffffff", gras=True)
    texte(lay, 'INSEE [% "code_insee" %] · [% format_number("pop_2022", 0) %] habitants (2022)',
          190, 6, 100, 8, 9, "#dce8f6")
    m = carte(lay, "Atlas communal", emprise_metropole, 8, 23, 180, 170)
    m.setAtlasDriven(True)
    m.setAtlasScalingMode(QgsLayoutItemMap.Auto)
    m.setAtlasMargin(0.10)
    habillage(lay, m, 11, 185, 176, 26, 2)
    loc = carte(lay, "Localisation", emprise_metropole, 194, 23, 95, 62)
    apercu = QgsLayoutItemMapOverview("Emprise", loc)
    apercu.setLinkedMap(m)
    apercu.setFrameSymbol(remplissage("184,38,43,60", "#b8262b", 0.5))
    loc.overviews().addOverview(apercu)
    texte(lay, INDICATEURS_ATLAS, 194, 90, 95, 62, html=True)
    leg = legende(lay, m, couches_leg, 194, 150, titre="")
    leg.setColumnCount(2)
    leg.setSplitLayer(True)
    for style, taille in ((QgsLegendStyle.Subgroup, 7.5), (QgsLegendStyle.SymbolLabel, 7)):
        police = QFont("Segoe UI")
        police.setBold(style == QgsLegendStyle.Subgroup)
        police.setPointSizeF(taille)
        leg.setStyleFont(style, police)
    leg.setSymbolHeight(3)
    leg.setSymbolWidth(5)
    leg.adjustBoxSize()
    texte(lay, "Sources : Cerema 2011-2025 ; IGN OCS GE 2019-2022, ADMIN EXPRESS ; "
               "Géoportail de l'Urbanisme (PLUi 04/05/2026) ; ASP RPG 2024 ; INSEE.", 8, 199, 200, 6, 7, "#52514e")
    texte(lay, f"{AUTEUR} · page [% @atlas_featurenumber %] / [% @atlas_totalfeatures %]",
          230, 199, 60, 6, 7, "#52514e")
    atlas = lay.atlas()
    atlas.setCoverageLayer(couverture)
    atlas.setEnabled(True)
    atlas.setHideCoverage(False)
    atlas.setPageNameExpression('"nom"')
    atlas.setFilenameExpression("'atlas_' || \"code_insee\" || '_' || \"nom\"")
    atlas.setSortFeatures(True)
    atlas.setSortExpression('"nom"')
    projet.layoutManager().addLayout(lay)
    return lay


INDICATEURS_DIVISIONS = """<div style="font-family:'Segoe UI';font-size:8.5pt;color:#1f1f1f;line-height:1.35">
<b style="color:#184f95">DIVISIONS INSCRITES AU CADASTRE (2018-2026)</b><br>
Parcelles divisées : <b>[% format_number("div_nb", 0) %]</b><br>
Lots créés : <b>[% format_number("div_lots", 0) %]</b><br>
Dont en zone U à dominante habitat : [% format_number("div_u_hab", 0) %]<br>
Divisions sur terrain déjà artificialisé (2019) : [% format_number("part_artif_pct", 0) %] %<br>
Divisions pour 100 ha de zone U : [% format_number("div_100ha_u", 1) %]
</div>"""


def atlas_divisions(projet, couverture, couches_leg, emprise_metropole):
    """Atlas séparé : une page par commune ayant au moins 5 divisions parcellaires."""
    lay = QgsPrintLayout(projet)
    lay.initializeDefaults()
    lay.setName("Atlas des divisions parcellaires 2018-2026")
    lay.pageCollection().page(0).setPageSize("A4", QgsLayoutItemPage.Landscape)
    rectangle(lay, 0, 0, 297, 18, BLEU)
    texte(lay, '[% "nom" %]', 8, 3, 180, 12, 18, "#ffffff", gras=True)
    texte(lay, 'Divisions parcellaires 2018-2026 · INSEE [% "code_insee" %]', 190, 6, 100, 8, 9, "#dce8f6")
    m = carte(lay, "Divisions parcellaires", emprise_metropole, 8, 23, 180, 170)
    m.setAtlasDriven(True)
    m.setAtlasScalingMode(QgsLayoutItemMap.Auto)
    m.setAtlasMargin(0.10)
    habillage(lay, m, 11, 185, 176, 26, 2)
    loc = carte(lay, "Localisation", emprise_metropole, 194, 23, 95, 62)
    apercu = QgsLayoutItemMapOverview("Emprise", loc)
    apercu.setLinkedMap(m)
    apercu.setFrameSymbol(remplissage("184,38,43,60", "#b8262b", 0.5))
    loc.overviews().addOverview(apercu)
    texte(lay, INDICATEURS_DIVISIONS, 194, 90, 95, 45, html=True)
    leg = legende(lay, m, couches_leg, 194, 138, titre="")
    texte(lay, "Méthode : parcelle de 2018 disparue en 2026 et couverte à 90 % ou plus par au moins deux "
               "nouvelles parcelles (cadastre Etalab). Sections remaniées exclues.", 194, 182, 95, 12, 7, "#52514e")
    texte(lay, "Sources : DGFiP, cadastre Etalab (02/01/2018, 01/09/2026) ; IGN OCS GE 2019, ADMIN EXPRESS ; "
               "Géoportail de l'Urbanisme (PLUi 04/05/2026).", 8, 199, 200, 6, 7, "#52514e")
    texte(lay, f"{AUTEUR} · page [% @atlas_featurenumber %] / [% @atlas_totalfeatures %]",
          230, 199, 60, 6, 7, "#52514e")
    atlas = lay.atlas()
    atlas.setCoverageLayer(couverture)
    atlas.setEnabled(True)
    atlas.setHideCoverage(False)
    atlas.setFilterFeatures(True)
    atlas.setFilterExpression('"div_nb" >= 5')
    atlas.setPageNameExpression('"nom"')
    atlas.setFilenameExpression("'divisions_' || \"code_insee\" || '_' || \"nom\"")
    atlas.setSortFeatures(True)
    atlas.setSortExpression('"nom"')
    projet.layoutManager().addLayout(lay)
    return lay


INDICATEURS_GISEMENTS = """<div style="font-family:'Segoe UI';font-size:8.5pt;color:#1f1f1f;line-height:1.35">
<b style="color:#184f95">POTENTIEL DANS LES ZONES U À DOMINANTE HABITAT</b><br>
Terrains repérés : <b>[% format_number("gis_nb", 0) %]</b> ([% format_number("gis_ha", 1) %] ha)<br>
Logements mobilisables à 10 ans : <b>≈ [% format_number("gis_log_mob", 0) %]</b><br>
Potentiel brut : [% format_number("gis_log_bruts", 0) %] logements<br>
Dents creuses : [% format_number("gis_nb_dc", 0) %] · divisions possibles : [% format_number("gis_nb_div", 0) %]
· grands tènements : [% format_number("gis_nb_gt", 0) %]<br>
[% CASE WHEN "tissu_dense" = 1 THEN '<i>Centre urbain dense : résultat à interpréter avec prudence.</i>' ELSE '' END %]
</div>"""


def atlas_gisements(projet, couverture, couches_leg, emprise_metropole):
    """Atlas séparé : une page par commune ayant au moins un gisement de densification."""
    lay = QgsPrintLayout(projet)
    lay.initializeDefaults()
    lay.setName("Atlas des gisements de densification")
    lay.pageCollection().page(0).setPageSize("A4", QgsLayoutItemPage.Landscape)
    rectangle(lay, 0, 0, 297, 18, BLEU)
    texte(lay, '[% "nom" %]', 8, 3, 180, 12, 18, "#ffffff", gras=True)
    texte(lay, 'Gisements de densification · INSEE [% "code_insee" %]', 190, 6, 100, 8, 9, "#dce8f6")
    m = carte(lay, "Gisements de densification", emprise_metropole, 8, 23, 180, 170)
    m.setAtlasDriven(True)
    m.setAtlasScalingMode(QgsLayoutItemMap.Auto)
    m.setAtlasMargin(0.10)
    habillage(lay, m, 11, 185, 176, 26, 2)
    loc = carte(lay, "Localisation", emprise_metropole, 194, 23, 95, 62)
    apercu = QgsLayoutItemMapOverview("Emprise", loc)
    apercu.setLinkedMap(m)
    apercu.setFrameSymbol(remplissage("184,38,43,60", "#b8262b", 0.5))
    loc.overviews().addOverview(apercu)
    texte(lay, INDICATEURS_GISEMENTS, 194, 90, 95, 48, html=True)
    leg = legende(lay, m, couches_leg, 194, 140, titre="")
    leg.setColumnCount(2)
    leg.setSplitLayer(True)
    for style, taille in ((QgsLegendStyle.Subgroup, 7.5), (QgsLegendStyle.SymbolLabel, 7)):
        police = QFont("Segoe UI")
        police.setBold(style == QgsLegendStyle.Subgroup)
        police.setPointSizeF(taille)
        leg.setStyleFont(style, police)
    leg.setSymbolHeight(3)
    leg.setSymbolWidth(5)
    leg.adjustBoxSize()
    texte(lay, "Repérage automatisé sans visite de terrain : pente, accès, réseaux, servitudes et volonté des "
               "propriétaires restent à vérifier.", 194, 184, 95, 10, 7, "#52514e")
    texte(lay, "Sources : DGFiP, cadastre Etalab (01/09/2026) ; IGN BD TOPO, OCS GE 2022, ADMIN EXPRESS ; "
               "Géoportail de l'Urbanisme (PLUi 04/05/2026).", 8, 199, 200, 6, 7, "#52514e")
    texte(lay, f"{AUTEUR} · page [% @atlas_featurenumber %] / [% @atlas_totalfeatures %]",
          230, 199, 60, 6, 7, "#52514e")
    atlas = lay.atlas()
    atlas.setCoverageLayer(couverture)
    atlas.setEnabled(True)
    atlas.setHideCoverage(False)
    atlas.setFilterFeatures(True)
    atlas.setFilterExpression('"gis_nb" > 0')
    atlas.setPageNameExpression('"nom"')
    atlas.setFilenameExpression("'gisements_' || \"code_insee\" || '_' || \"nom\"")
    atlas.setSortFeatures(True)
    atlas.setSortExpression('"nom"')
    projet.layoutManager().addLayout(lay)
    return lay


def theme(projet, nom, couches):
    rec = QgsMapThemeCollection.MapThemeRecord()
    rec.setLayerRecords([QgsMapThemeCollection.MapThemeLayerRecord(lyr) for lyr in couches])
    projet.mapThemeCollection().insert(nom, rec)


# --- Construction -----------------------------------------------------------------------------
def construire():
    projet = QgsProject.instance()
    projet.clear()
    projet.setCrs(QgsCoordinateReferenceSystem("EPSG:2154"))
    projet.setTitle("Diagnostic foncier ZAN - Métropole Rouen Normandie")
    racine = projet.layerTreeRoot()

    # habillage sans fond de carte externe (même style que les planches PDF) :
    # gris clair hors territoire (fond du cadre), aplat crème pour la Métropole, Seine en bleu
    territoire = couche("perimetre_metropole", "Fond du territoire")
    territoire.setRenderer(QgsSingleSymbolRenderer(remplissage("#f6f5f1", "#f6f5f1", 0)))
    eau = couche("surfaces_eau", "Seine et plans d'eau")
    eau.setRenderer(QgsSingleSymbolRenderer(remplissage("#cfe0ee", "#cfe0ee", 0)))
    eau_legende[:] = [eau]

    perim = couche("perimetre_metropole", "Périmètre de la Métropole")
    perim.setRenderer(QgsSingleSymbolRenderer(remplissage("#000000", "#0b0b0b", 0.6, style="no")))
    limites = couche_limites()
    masque = couche_masque_atlas()
    cercles, destinations = couche_cercles()
    rythme = couche("communes_indicateurs", "Évolution du rythme de consommation depuis 2021")
    categories(rythme, "classe_effort", EFFORT, opacite=0.9)
    flux = couche("ocsge_flux_2019_2022", "Artificialisation 2019-2022 (OCS GE)")
    categories(flux, "type_flux", FLUX, contour=None, largeur=0.3)
    zon = couche("plui_zonage_qualifie", "Zonage PLUi simplifié")
    categories(zon, "famille", ZONES, opacite=0.45)
    au = couche("plui_zones_au", "Zones à urbaniser par vocation")
    categories(au, "vocation", VOCATIONS, contour="#0b0b0b")
    gis = couche("gisements_densification", "Gisements de densification")
    categories(gis, "type_gisement", GISEMENTS)
    cont = couche("contraintes_prescriptions", "Prescriptions excluantes (PLUi)")
    cont.setRenderer(QgsSingleSymbolRenderer(remplissage("#4f8f4a", "#4f8f4a", 0.2, opacite=0.7, style="dense6")))
    bati = couche("bdtopo_batiments_etude", "Bâtiments (BD TOPO)")
    bati.setRenderer(QgsSingleSymbolRenderer(remplissage("#6b6a66", "#6b6a66", 0)))
    div = couche("divisions_parcellaires", "Parcelles divisées 2018-2026")
    categories(div, "categorie", CATEGORIES_DIV, opacite=0.85, contour=None, largeur=0.3)
    lots = couche("lots_issus_divisions", "Lots issus des divisions")
    lots.setRenderer(QgsSingleSymbolRenderer(remplissage("255,255,255,0", "#1f1f1f", 0.2)))
    parc = couche("cadastre_parcelles_etude", "Parcelles cadastrales")
    parc.setRenderer(QgsSingleSymbolRenderer(remplissage("255,255,255,0", "#cfccc4", 0.1)))

    # arbre des couches : le premier groupe créé est dessiné au-dessus
    groupes = [
        ("Habillage atlas", [(masque, False)]),
        ("Divisions parcellaires 2018-2026", [(lots, False), (div, False)]),
        ("Densification (gisements : 71 communes ; bâti et cadastre : communes test)",
         [(gis, False), (cont, False), (bati, False), (parc, False)]),
        ("PLUi", [(au, True), (zon, False)]),
        ("Diagnostic ZAN", [(perim, True), (cercles, True), (destinations, False), (eau, True),
                            (limites, True), (flux, False), (rythme, False)]),
        ("Fond", [(territoire, True)]),
    ]
    for nom_groupe, couches in groupes:
        g = racine.addGroup(nom_groupe)
        for lyr, visible in couches:
            projet.addMapLayer(lyr, False)
            g.addLayer(lyr).setItemVisibilityChecked(visible)

    # thèmes de carte (un par planche)
    theme(projet, "C01 Consommation ENAF", [perim, cercles, eau, limites, territoire])
    theme(projet, "C02 Rythme depuis 2021", [perim, eau, limites, rythme, territoire])
    theme(projet, "C06 Réservoir zones AU", [au, perim, eau, limites, territoire])
    theme(projet, "C08 Densification", [gis, cont, bati, parc, au, eau, limites, territoire])
    theme(projet, "Atlas communal", [masque, gis, au, flux, zon, eau, territoire])
    theme(projet, "Localisation", [perim, limites, territoire])
    theme(projet, "Divisions parcellaires", [masque, lots, div, eau, territoire])
    theme(projet, "Gisements de densification", [masque, gis, au, eau, territoire])

    met = perim.extent()
    met.grow(1500)
    bg = [f for f in limites.getFeatures(QgsFeatureRequest().setFilterExpression("\"nom\" = 'Bois-Guillaume'"))]
    emprise_bg = bg[0].geometry().boundingBox()
    emprise_bg.grow(250)
    src = "Cerema 2011-2025 ; IGN ADMIN EXPRESS, OCS GE 2022 (surfaces en eau) ; Géoportail de l'Urbanisme (PLUi 04/05/2026)"
    planche_a3(projet, "Planche A3 - C01 Consommation d'ENAF 2011-2021",
               "Consommation d'espaces naturels, agricoles et forestiers",
               "Période de référence de la loi Climat et Résilience : 2011-2021",
               "C01 Consommation ENAF", met, [cercles, destinations],
               "<p style=\"font-family:'Segoe UI'\"><b style='color:#184f95'>LECTURE</b><br>"
               "665 ha consommés entre 2011 et 2021, dont 55 % pour l'habitat. La surface des cercles "
               "est proportionnelle aux hectares consommés ; la couleur indique la destination dominante.</p>",
               src)
    planche_a3(projet, "Planche A3 - C02 Rythme de consommation depuis 2021",
               "Rythme de consommation depuis 2021",
               "Évolution du rythme annuel 2021-2024 par rapport à 2011-2020 (objectif national : -50 %)",
               "C02 Rythme depuis 2021", met, [rythme],
               "<p style=\"font-family:'Segoe UI'\"><b style='color:#184f95'>À RETENIR</b><br>"
               "Rythme en baisse de 30 % à l'échelle de la Métropole, pour un objectif de -50 %. "
               "L'objectif s'apprécie à l'échelle du SCoT et du PLUi, pas commune par commune.</p>",
               src)
    planche_a3(projet, "Planche A3 - C06 Réservoir foncier des zones AU",
               "Le réservoir foncier des zones à urbaniser",
               "Zones AU du PLUi selon leur vocation",
               "C06 Réservoir zones AU", met, [au],
               "<p style=\"font-family:'Segoe UI'\"><b style='color:#184f95'>À RETENIR</b><br>"
               "575 ha de zones AU encore non artificialisés en 2022, soit 3,9 fois l'enveloppe ZAN "
               "restante jusqu'en 2031 (147 ha).</p>",
               src + " ; ASP RPG 2024")
    planche_a3(projet, "Planche A3 - C08 Densification Bois-Guillaume",
               "Gisements fonciers de densification : Bois-Guillaume",
               "Repérage automatisé dans les zones urbaines à dominante habitat du PLUi",
               "C08 Densification", emprise_bg, [gis, cont, au, bati],
               "<p style=\"font-family:'Segoe UI'\"><b style='color:#184f95'>HYPOTHÈSES</b><br>"
               "Recul de 5 m autour du bâti, lot de 400 m² minimum pouvant contenir un carré de 15 m, "
               "accès d'au moins 4 m sur la voie. Résultat à valider sur le terrain.</p>",
               "DGFiP/IGN Parcellaire Express ; IGN BD TOPO, OCS GE 2022 ; Géoportail de l'Urbanisme", km=1)
    atlas_a4(projet, limites, [zon, flux, gis], met)
    atlas_divisions(projet, limites, [div, lots], met)
    atlas_gisements(projet, limites, [gis, au], met)

    # modèles du modeleur graphique, intégrés au projet
    modeles = RACINE / "scripts" / "08_modeles_traitement.py"
    if modeles.exists():
        ns = {"RACINE_PROJET": str(RACINE), "__name__": "modeles_zan"}
        exec(modeles.read_text(encoding="utf-8"), ns)
        ns["construire_modeles"](integrer_au_projet=True)

    projet.writeEntry("Paths", "/Absolute", False)  # chemins relatifs
    chemin = DOSSIER / "diagnostic_zan_rouen.qgz"
    projet.write(str(chemin))
    return chemin


if __name__ in ("__main__", "__console__"):
    print(construire())
