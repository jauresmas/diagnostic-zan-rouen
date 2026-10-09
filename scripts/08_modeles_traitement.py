"""Étape 8 (optionnelle) - Modèles de traitement QGIS (modeleur graphique).

À exécuter dans QGIS. Construit deux modèles .model3, éditables dans le modeleur
graphique (équivalent du ModelBuilder d'ArcGIS Pro) :

  1. ZAN_bilan_artificialisation_secteur : pour un périmètre quelconque (projet,
     quartier, groupe de communes), surfaces artificialisées et désartificialisées
     entre 2019 et 2022 d'après l'OCS GE. Outil d'appui aux agents.
  2. ZAN_espaces_libres_zone_U : version modeleur du repérage des espaces libres
     constructibles (étape 4) : zones U habitat, recul autour du bâti, prescriptions
     excluantes, ouverture morphologique, surface minimale. Tous les seuils sont des
     paramètres du modèle.

Les modèles sont enregistrés dans livrables/02_Donnees_SIG/modeles/ et intégrés au
projet QGIS (fournisseur « Modèles du projet » de la boîte à outils).
"""
from pathlib import Path

from qgis.core import (QgsProcessing, QgsProcessingModelAlgorithm, QgsProcessingModelChildAlgorithm,
                       QgsProcessingModelChildParameterSource as Source, QgsProcessingModelOutput,
                       QgsProcessingModelParameter, QgsProcessingParameterNumber,
                       QgsProcessingParameterVectorLayer)
from qgis.PyQt.QtCore import QPointF

try:
    RACINE = Path(__file__).resolve().parents[1]
except NameError:  # exécution depuis la console QGIS
    RACINE = Path(globals().get("RACINE_PROJET", "."))
GPKG = RACINE / "livrables" / "02_Donnees_SIG" / "diagnostic_zan_rouen.gpkg"
DOSSIER_MODELES = RACINE / "livrables" / "02_Donnees_SIG" / "modeles"
GROUPE = "Diagnostic foncier ZAN"


def couche_defaut(nom):
    return f"{GPKG}|layername={nom}"


def parametre(modele, definition, x, y):
    composant = QgsProcessingModelParameter(definition.name())
    composant.setPosition(QPointF(x, y))
    modele.addModelParameter(definition, composant)


def etape(modele, identifiant, algo, description, x, y, sources, sorties=None):
    """Ajoute un algorithme enfant. sources : {paramètre: Source}. sorties : {nom: sortie_algo}."""
    enfant = QgsProcessingModelChildAlgorithm(algo)
    enfant.setChildId(identifiant)
    enfant.setDescription(description)
    enfant.setPosition(QPointF(x, y))
    for nom, source in sources.items():
        enfant.addParameterSources(nom, [source])
    if sorties:
        resultats = {}
        for nom, sortie in sorties.items():
            o = QgsProcessingModelOutput(nom)
            o.setChildOutputName(sortie)
            o.setChildId(identifiant)
            o.setPosition(QPointF(x + 160, y + 60))
            resultats[nom] = o
        enfant.setModelOutputs(resultats)
    modele.addChildAlgorithm(enfant)
    return identifiant


def sortie_de(identifiant, nom="OUTPUT"):
    return Source.fromChildOutput(identifiant, nom)


def modele_bilan_secteur():
    m = QgsProcessingModelAlgorithm("ZAN - Bilan d'artificialisation d'un secteur", GROUPE)
    parametre(m, QgsProcessingParameterVectorLayer(
        "secteur", "Secteur d'étude (polygone)", [QgsProcessing.TypeVectorPolygon]), 120, 60)
    parametre(m, QgsProcessingParameterVectorLayer(
        "flux", "Flux OCS GE 2019-2022", [QgsProcessing.TypeVectorPolygon],
        defaultValue=couche_defaut("ocsge_flux_2019_2022")), 420, 60)
    etape(m, "decoupage", "native:intersection", "Découper les flux par le secteur", 270, 170, {
        "INPUT": Source.fromModelParameter("flux"),
        "OVERLAY": Source.fromModelParameter("secteur"),
        "OVERLAY_FIELDS_PREFIX": Source.fromStaticValue("secteur_"),
    })
    etape(m, "surface", "native:fieldcalculator", "Calculer la surface (ha)", 270, 280, {
        "INPUT": sortie_de("decoupage"),
        "FIELD_NAME": Source.fromStaticValue("surface_secteur_ha"),
        "FIELD_TYPE": Source.fromStaticValue(0),
        "FIELD_LENGTH": Source.fromStaticValue(12),
        "FIELD_PRECISION": Source.fromStaticValue(3),
        "FORMULA": Source.fromStaticValue("$area / 10000"),
    }, {"Flux dans le secteur": "OUTPUT"})
    etape(m, "bilan", "qgis:statisticsbycategories", "Totaliser par type de flux", 270, 400, {
        "INPUT": sortie_de("surface"),
        "VALUES_FIELD_NAME": Source.fromStaticValue("surface_secteur_ha"),
        "CATEGORIES_FIELD_NAME": Source.fromStaticValue(["type_flux"]),
    }, {"Bilan artificialisation (ha)": "OUTPUT"})
    m.setHelpContent({
        "ALG_DESC": "Calcule, pour un secteur quelconque, les surfaces artificialisées et désartificialisées "
                    "entre 2019 et 2022 (OCS GE IGN, classement selon le décret n° 2023-1096). "
                    "Le tableau de sortie donne la somme (champ sum) par type de flux.",
        "secteur": "Polygone(s) du secteur : périmètre de projet, quartier, commune...",
        "flux": "Couche ocsge_flux_2019_2022 du GeoPackage livré (valeur par défaut).",
        "ALG_CREATOR": "Jauresmas",
    })
    return m


def modele_espaces_libres():
    m = QgsProcessingModelAlgorithm("ZAN - Espaces libres constructibles en zone U", GROUPE)
    entrees = [
        ("zonage", "Zonage du PLUi", "plui_zonage_qualifie", 60),
        ("parcelles", "Parcelles cadastrales", "cadastre_parcelles_etude", 260),
        ("batiments", "Bâtiments", "bdtopo_batiments_etude", 460),
        ("contraintes", "Prescriptions excluantes", "contraintes_prescriptions", 660),
    ]
    for nom, lib, defaut, x in entrees:
        parametre(m, QgsProcessingParameterVectorLayer(nom, lib, [QgsProcessing.TypeVectorPolygon],
                                                       defaultValue=couche_defaut(defaut)), x, 50)
    for nom, lib, val, x in (("recul_bati", "Recul autour du bâti (m)", 5, 860),
                             ("largeur_lot", "Largeur minimale d'un lot (m)", 15, 860),
                             ("surface_min", "Surface minimale d'un lot (m²)", 400, 860)):
        parametre(m, QgsProcessingParameterNumber(nom, lib, QgsProcessingParameterNumber.Double,
                                                  defaultValue=val, minValue=0),
                  x, {"recul_bati": 50, "largeur_lot": 110, "surface_min": 170}[nom])

    etape(m, "zones_u", "native:extractbyexpression", "Zones U à dominante habitat", 60, 170, {
        "INPUT": Source.fromModelParameter("zonage"),
        "EXPRESSION": Source.fromStaticValue(
            "\"famille\" = 'U' AND regexp_match(\"libelle\", '^(UA|UB|UC|UD|UR)') "
            "AND left(\"libelle\", 3) <> 'URX'"),
    })
    etape(m, "parcelles_u", "native:clip", "Parcelles découpées par les zones U", 260, 270, {
        "INPUT": Source.fromModelParameter("parcelles"),
        "OVERLAY": sortie_de("zones_u"),
    })
    etape(m, "tampon_bati", "native:buffer", "Recul autour du bâti", 460, 170, {
        "INPUT": Source.fromModelParameter("batiments"),
        "DISTANCE": Source.fromModelParameter("recul_bati"),
        "SEGMENTS": Source.fromStaticValue(5),
        # pas de fusion : la différence s'appuie alors sur l'index spatial (bien plus rapide)
        "DISSOLVE": Source.fromStaticValue(False),
    })
    etape(m, "sans_bati", "native:difference", "Retirer le bâti et son recul", 360, 380, {
        "INPUT": sortie_de("parcelles_u"),
        "OVERLAY": sortie_de("tampon_bati"),
    })
    etape(m, "sans_contraintes", "native:difference", "Retirer les prescriptions excluantes", 560, 470, {
        "INPUT": sortie_de("sans_bati"),
        "OVERLAY": Source.fromModelParameter("contraintes"),
    })
    etape(m, "reparation_1", "native:fixgeometries", "Réparer les géométries", 760, 470, {
        "INPUT": sortie_de("sans_contraintes"),
    })
    etape(m, "erosion", "native:buffer", "Ouverture (1/2) : érosion", 560, 570, {
        "INPUT": sortie_de("reparation_1"),
        "DISTANCE": Source.fromExpression("-@largeur_lot / 2"),
        "SEGMENTS": Source.fromStaticValue(5),
        "JOIN_STYLE": Source.fromStaticValue(1),
        "DISSOLVE": Source.fromStaticValue(False),
    })
    etape(m, "dilatation", "native:buffer", "Ouverture (2/2) : dilatation", 560, 670, {
        "INPUT": sortie_de("erosion"),
        "DISTANCE": Source.fromExpression("@largeur_lot / 2"),
        "SEGMENTS": Source.fromStaticValue(5),
        "JOIN_STYLE": Source.fromStaticValue(1),
        "DISSOLVE": Source.fromStaticValue(False),
    })
    etape(m, "reparation_2", "native:fixgeometries", "Réparer les géométries", 760, 670, {
        "INPUT": sortie_de("dilatation"),
    })
    etape(m, "recalage", "native:clip", "Recaler sur l'espace libre", 360, 670, {
        "INPUT": sortie_de("reparation_2"),
        "OVERLAY": sortie_de("reparation_1"),
    })
    etape(m, "morceaux", "native:multiparttosingleparts", "Séparer les espaces libres", 360, 770, {
        "INPUT": sortie_de("recalage"),
    })
    # la séparation duplique le champ fid hérité du GeoPackage : à supprimer avant écriture
    etape(m, "sans_fid", "native:deletecolumn", "Supprimer le champ fid dupliqué", 560, 770, {
        "INPUT": sortie_de("morceaux"),
        "COLUMN": Source.fromStaticValue(["fid"]),
    })
    etape(m, "surface", "native:fieldcalculator", "Calculer la surface (m²)", 360, 870, {
        "INPUT": sortie_de("sans_fid"),
        "FIELD_NAME": Source.fromStaticValue("surface_libre_m2"),
        "FIELD_TYPE": Source.fromStaticValue(0),
        "FIELD_LENGTH": Source.fromStaticValue(12),
        "FIELD_PRECISION": Source.fromStaticValue(0),
        "FORMULA": Source.fromStaticValue("round($area, 0)"),
    })
    etape(m, "filtre", "native:extractbyexpression", "Garder les lots assez grands", 360, 970, {
        "INPUT": sortie_de("surface"),
        "EXPRESSION": Source.fromExpression(
            "'\"surface_libre_m2\" >= ' || to_string(@surface_min)"),
    }, {"Espaces libres constructibles": "OUTPUT"})
    m.setHelpContent({
        "ALG_DESC": "Repère les espaces libres constructibles dans les zones urbaines à dominante habitat "
                    "du PLUi : parcelles moins le bâti et son recul, moins les prescriptions excluantes "
                    "(EBC, patrimoine paysager, risques), puis ouverture morphologique pour ne garder que "
                    "les espaces où un lot de la largeur minimale peut s'inscrire. Version simplifiée de "
                    "l'étape 4 du diagnostic (sans critère d'accès à la voie ni typologie).",
        "recul_bati": "Distance minimale entre un nouveau lot et le bâti existant.",
        "largeur_lot": "Côté du carré qui doit pouvoir s'inscrire dans l'espace libre.",
        "surface_min": "Surface en dessous de laquelle un espace libre n'est pas retenu.",
        "ALG_CREATOR": "Jauresmas",
    })
    return m


def construire_modeles(integrer_au_projet=True):
    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    chemins = []
    for fichier, fabrique in (("ZAN_bilan_artificialisation_secteur.model3", modele_bilan_secteur),
                              ("ZAN_espaces_libres_zone_U.model3", modele_espaces_libres)):
        modele = fabrique()
        modele.updateDestinationParameters()
        chemin = DOSSIER_MODELES / fichier
        modele.toFile(str(chemin))
        chemins.append(chemin)
        if integrer_au_projet:
            from qgis.core import QgsApplication
            fournisseur = QgsApplication.processingRegistry().providerById("project")
            if fournisseur is not None:
                fournisseur.add_model(modele)
    return chemins


if __name__ in ("__main__", "__console__"):
    print(construire_modeles())
