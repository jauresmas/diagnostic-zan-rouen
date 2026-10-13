"""Étape 6 - Documents d'accompagnement (PDF) : note méthodologique, fiche tutoriel,
bordereau de livraison. Les chiffres sont lus dans les synthèses produites par les
étapes 1 à 4 : relancer la chaîne met donc automatiquement les documents à jour.
"""
import json
from datetime import date
from pathlib import Path

import matplotlib
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

import config
from cartes import fr, pct
from outils import log

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
AUJOURDHUI = f"{MOIS[date.today().month - 1]} {date.today().year}"
VERSION = "1.0"
BLEU = colors.HexColor("#184f95")
BLEU_PALE = colors.HexColor("#dce8f6")
GRIS = colors.HexColor("#52514e")
GRIS_CLAIR = colors.HexColor("#e1e0d9")
FOND = colors.HexColor("#f6f5f1")
ROUGE = colors.HexColor("#b8262b")
DOSSIER_DOC = config.LIVRABLES / "01_Documents"


# --- Polices et styles ------------------------------------------------------------------------
def polices():
    win = Path("C:/Windows/Fonts")
    if (win / "segoeui.ttf").exists():
        fichiers = (win / "segoeui.ttf", win / "segoeuib.ttf", win / "segoeuii.ttf")
    else:  # repli multiplateforme : DejaVu, livrée avec matplotlib
        d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        fichiers = (d / "DejaVuSans.ttf", d / "DejaVuSans-Bold.ttf", d / "DejaVuSans-Oblique.ttf")
    for nom, f in zip(("Texte", "Texte-Gras", "Texte-Italique"), fichiers):
        pdfmetrics.registerFont(TTFont(nom, str(f)))
    pdfmetrics.registerFontFamily("Texte", normal="Texte", bold="Texte-Gras", italic="Texte-Italique",
                                  boldItalic="Texte-Gras")


polices()
ST = {
    "corps": ParagraphStyle("corps", fontName="Texte", fontSize=9.5, leading=14.2, alignment=TA_JUSTIFY,
                            spaceAfter=6, textColor=colors.HexColor("#1f1f1f")),
    "h1": ParagraphStyle("h1", fontName="Texte-Gras", fontSize=15, leading=19, textColor=BLEU,
                         spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Texte-Gras", fontSize=11, leading=14, textColor=colors.black,
                         spaceBefore=8, spaceAfter=5),
    "puce": ParagraphStyle("puce", fontName="Texte", fontSize=9.5, leading=14, leftIndent=12,
                           bulletIndent=2, spaceAfter=2),
    "legende": ParagraphStyle("legende", fontName="Texte-Italique", fontSize=8, leading=10.5,
                              textColor=GRIS, spaceBefore=3, spaceAfter=10),
    "cellule": ParagraphStyle("cellule", fontName="Texte", fontSize=8.3, leading=10.8),
    "cellule_g": ParagraphStyle("cellule_g", fontName="Texte-Gras", fontSize=8.3, leading=10.8,
                                textColor=colors.white),
    "encadre": ParagraphStyle("encadre", fontName="Texte", fontSize=9.3, leading=13.5),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.5, leading=11, backColor=FOND,
                           borderPadding=6, leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=8),
}


def P(texte, style="corps"):
    return Paragraph(texte, ST[style])


def puces(items):
    return [Paragraph(t, ST["puce"], bulletText="•") for t in items]


def tableau(lignes, largeurs, entete=True):
    data = [[Paragraph(str(c), ST["cellule_g" if (entete and i == 0) else "cellule"]) for c in ligne]
            for i, ligne in enumerate(lignes)]
    t = Table(data, colWidths=largeurs, repeatRows=1 if entete else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIS_CLAIR),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if entete:
        style.append(("BACKGROUND", (0, 0), (-1, 0), BLEU))
    t.setStyle(TableStyle(style))
    return t


def encadre(texte, couleur=BLEU_PALE):
    t = Table([[Paragraph(texte, ST["encadre"])]], colWidths=[17 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), couleur),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def figure(chemin_png, legende, largeur=17 * cm):
    """Insère une vignette JPEG allégée (1 800 px) de la figure."""
    vignettes = config.INTERIM / "vignettes"
    vignettes.mkdir(parents=True, exist_ok=True)
    cible = vignettes / (chemin_png.stem + ".jpg")
    with PILImage.open(chemin_png) as im:
        im = im.convert("RGB")
        im.thumbnail((1800, 1800))
        im.save(cible, quality=86, optimize=True)
        w, h = im.size
    return KeepTogether([Image(str(cible), width=largeur, height=largeur * h / w), P(legende, "legende")])


# --- Gabarit de page ------------------------------------------------------------------------------
def gabarit(titre_doc):
    def pages(canv, doc):
        canv.saveState()
        canv.setStrokeColor(GRIS_CLAIR)
        canv.setLineWidth(0.5)
        canv.line(2 * cm, A4[1] - 1.4 * cm, A4[0] - 2 * cm, A4[1] - 1.4 * cm)
        canv.setFont("Texte", 7.5)
        canv.setFillColor(GRIS)
        canv.drawString(2 * cm, A4[1] - 1.2 * cm, titre_doc)
        canv.drawRightString(A4[0] - 2 * cm, A4[1] - 1.2 * cm, f"{config.EPCI_NOM} · v{VERSION}")
        canv.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
        canv.drawString(2 * cm, 1.0 * cm, f"{config.AUTEUR} · {AUJOURDHUI} · étude indépendante, document non officiel")
        canv.drawRightString(A4[0] - 2 * cm, 1.0 * cm, f"{doc.page}")
        canv.restoreState()
    return pages


def couverture(titre, sous_titre, lignes):
    def dessiner(canv, doc):
        canv.saveState()
        canv.setFillColor(BLEU)
        canv.rect(0, A4[1] * 0.42, A4[0], A4[1] * 0.58, fill=1, stroke=0)
        canv.setFillColor(colors.white)
        canv.setFont("Texte", 11)
        canv.drawString(2.2 * cm, A4[1] - 3.2 * cm, "DIAGNOSTIC FONCIER · ZÉRO ARTIFICIALISATION NETTE")
        canv.setFont("Texte-Gras", 28)
        y = A4[1] - 7 * cm
        for ligne in titre.split("\n"):
            canv.drawString(2.2 * cm, y, ligne)
            y -= 1.15 * cm
        canv.setFillColor(BLEU_PALE)
        canv.setFont("Texte", 13)
        canv.drawString(2.2 * cm, y - 0.4 * cm, sous_titre)
        canv.setFillColor(colors.HexColor("#1f1f1f"))
        canv.setFont("Texte", 10.5)
        y = A4[1] * 0.42 - 1.8 * cm
        for lib, val in lignes:
            canv.setFillColor(GRIS)
            canv.drawString(2.2 * cm, y, lib)
            canv.setFillColor(colors.black)
            canv.drawString(7.2 * cm, y, val)
            y -= 0.75 * cm
        canv.setFont("Texte-Italique", 8.5)
        canv.setFillColor(GRIS)
        canv.drawString(2.2 * cm, 2.2 * cm, "Étude indépendante réalisée à partir de données ouvertes. "
                                            "Ce document n'engage pas la Métropole Rouen Normandie.")
        canv.restoreState()
    return dessiner


def construire(chemin, titre_doc, couv, histoire):
    doc = SimpleDocTemplate(str(chemin), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=titre_doc, author=config.AUTEUR,
                            subject=f"Diagnostic foncier ZAN - {config.EPCI_NOM}")
    doc.build([PageBreak()] + histoire, onFirstPage=couv, onLaterPages=gabarit(titre_doc))
    log(f"  {chemin.name}")


# --- Note méthodologique ------------------------------------------------------------------------
def section_divisions(s, F, G):
    """Section 6 bis : divisions parcellaires observées (étape 4 bis)."""
    a0, a1 = config.CADASTRE_MILLESIMES
    H = [P("6 bis. Divisions parcellaires observées 2018-2026", "h1")]
    H += [P("<b>Pourquoi.</b> La division parcellaire est l'autre visage du ZAN : elle densifie le tissu "
            "pavillonnaire sans consommer d'ENAF quand le terrain est déjà un jardin. Les déclarations préalables "
            "de division ne sont pas publiées en données ouvertes ; on repère donc les divisions effectivement "
            f"inscrites au cadastre en comparant les millésimes Etalab du {a0} et du {a1}.")]
    H += [tableau([
        ["Critère", "Règle appliquée"],
        ["Division", f"Parcelle de {a0[:4]} disparue en {a1[:4]}, couverte à au moins "
                     f"{pct(config.COUVERTURE_MIN_DIVISION * 100)} par 2 nouvelles parcelles ou plus"],
        ["Date", "Date de création des nouvelles parcelles au cadastre (après la vente ou le bornage)"],
        ["Remaniements", f"Section exclue si plus de {pct(config.SEUIL_REMANIEMENT * 100)} de ses parcelles "
                         "changent de numéro (renumérotation, pas division)"],
        ["Qualification", "Zone du PLUi majoritaire ; part de la parcelle déjà artificialisée en 2019 (OCS GE)"],
    ], [3.4 * cm, 13.6 * cm])]
    cat = s["par_categorie"]
    H += [Spacer(1, 8), encadre(
        f"<b>{fr(s['nb_divisions'], 0)} parcelles divisées</b> entre {a0[:4]} et {a1[:4]}, créant "
        f"{fr(s['lots_crees'], 0)} lots supplémentaires sur {fr(s['surface_divisee_ha'], 0, 'ha')}. "
        f"{pct(s['part_u_habitat'] * 100)} se trouvent en zone U à dominante habitat "
        f"({fr(cat.get('U habitat', 0), 0)} divisions, parcelle médiane de "
        f"{fr(s['surface_mediane_u_hab_m2'], 0)} m²). <b>{pct(s['part_div_deja_artif'] * 100)} des divisions portent "
        f"sur des terrains déjà artificialisés en 2019</b> ({pct(s['part_u_hab_deja_artif'] * 100)} en zone U habitat) : "
        "jardins, cours ou parcelles bâties, densifiés sans consommation d'ENAF. Les divisions en zone A ou N "
        "concernent surtout de grandes parcelles agricoles (successions, ventes partielles). "
        f"{fr(s['sections_remaniees_exclues'], 0)} sections remaniées ont été écartées.")]
    H += [Spacer(1, 8), figure(G / "G06_Divisions_parcellaires_par_annee.png",
                               "Figure 9 - Parcelles divisées par année et par zone du PLUi.")]
    H += [figure(F / "C09_Divisions_parcellaires_2018-2026.png",
                 "Figure 10 - Planche C09 : nombre de parcelles divisées par commune.")]
    lignes = [["Commune test", "Grandes parcelles U habitat en 2018", "Divisées depuis",
               "Taux observé", "Ramené à 10 ans", "Hypothèse du modèle"]]
    for nom, c in s["calibration"].items():
        lignes.append([nom, fr(c["parcelles_candidates_2018"], 0), fr(c["divisees"], 0),
                       pct(c["taux_periode_pct"], 1), pct(c["taux_10_ans_pct"], 1),
                       pct(s["hypothese_mobilisation_10_ans_pct"])])
    H += [P("Calibration du modèle de densification", "h2"),
          P(f"Parmi les parcelles de plus de {fr(config.SURFACE_MIN_DIVISION_M2)} m² situées en zone U à dominante "
            "habitat en 2018, la part effectivement divisée donne un ordre de grandeur du taux de mobilisation "
            "réel, à comparer à l'hypothèse retenue à l'étape 4 (qui ne porte que sur les parcelles remplissant "
            "tous les critères du modèle) :"),
          tableau(lignes, [3 * cm, 3.4 * cm, 2.4 * cm, 2.4 * cm, 2.6 * cm, 3.2 * cm])]
    H += [Spacer(1, 6), P("<b>Limites.</b> Le cadastre enregistre les divisions réalisées, pas les autorisations "
                          "déposées : une déclaration préalable non suivie d'effet n'apparaît pas, et la date "
                          "observée suit la vente de quelques mois. Certaines divisions ne relèvent pas de la "
                          "densification (successions, régularisations). Le croisement avec les déclarations "
                          "préalables issues du logiciel d'instruction (ADS) permettrait de suivre toute la "
                          "chaîne, du dépôt à la construction.")]
    H += [PageBreak()]
    return H


def note_methodologique(s1, s2, s3, s4, s4b=None):
    F = config.LIVRABLES / "03_Planches_cartographiques"
    G = config.LIVRABLES / "04_Graphiques"
    restant = s3["enveloppe_restante_ha"]
    communes = list(config.COMMUNES_DENSIFICATION.values())
    tot_gis = sum(v["nb_gisements"] for v in s4.values())
    tot_ha = sum(v["surface_ha"] for v in s4.values())
    tot_log = sum(v["logements_mobilisables"] for v in s4.values())
    moment = ("début", "mi-", "fin")[min(2, int((s1["annee_epuisement"] % 1) * 3))]
    epuisement = f"{moment}{'' if moment.endswith('-') else ' '}{int(s1['annee_epuisement'])}"
    H = []
    H += [P("Sommaire", "h1")]
    H += puces(["1. Contexte et objectifs", "2. Données mobilisées", "3. Consommation d'espaces 2011-2025",
                "4. Artificialisation des sols 2019-2022", "5. Le PLUi face à la trajectoire ZAN",
                "6. Gisements de densification", "6 bis. Divisions parcellaires observées 2018-2026",
                "7. Chaîne de traitement et mise à jour",
                "8. Limites et précautions d'usage", "9. Pistes de prolongement", "Annexe : liste des livrables"])
    H += [Spacer(1, 14), P("Les chiffres à retenir", "h2")]
    H += [tableau([
        ["Indicateur", "Valeur", "Source"],
        ["Consommation d'ENAF 2011-2021 (période de référence)", fr(s1["conso_1121_ha"], 0, "ha"), "Cerema"],
        ["Consommation d'ENAF 2021-2025", fr(s1["conso_2125_ha"], 0, "ha"), "Cerema"],
        ["Évolution du rythme annuel (objectif -50 %)", pct(s1["evol_rythme_pct"], signe=True), "Cerema"],
        ["Part de l'enveloppe indicative 2021-2031 utilisée au 01/01/2025", pct(s1["part_enveloppe"] * 100), "Calcul"],
        ["Épuisement de l'enveloppe au rythme actuel", epuisement, "Projection"],
        ["Artificialisation nette 2019-2022", fr(s2["artif_nette_ha"], 0, "ha"), "IGN OCS GE"],
        ["Zones AU du PLUi non artificialisées (2022)", fr(s3["au_non_artif_ha"], 0, "ha"), "GPU, OCS GE"],
        ["Enveloppe restante 2025-2031", fr(restant, 0, "ha"), "Calcul"],
        [f"Gisements de densification ({' et '.join(communes)})",
         f"{tot_gis} terrains, {fr(tot_ha, 0, 'ha')}", "Cadastre, BD TOPO"],
    ], [10 * cm, 4 * cm, 3 * cm])]
    H += [PageBreak()]

    # 1
    H += [P("1. Contexte et objectifs", "h1")]
    H += [P("La loi Climat et Résilience du 22 août 2021 fixe l'objectif de <b>zéro artificialisation nette "
            "(ZAN) en 2050</b>. Pour la première décennie (2021-2031), elle demande de diviser par deux la "
            "consommation d'espaces naturels, agricoles et forestiers (ENAF) par rapport à la décennie "
            "2011-2021. Cet objectif est décliné successivement dans le SRADDET, le SCoT puis les PLU(i), "
            "qui doivent l'intégrer avant le 22 février 2028. Le cadre est encore en discussion au Parlement : "
            "d'après les informations disponibles à la date de rédaction, la proposition de loi « TRACE », "
            "adoptée par le Sénat en mars 2025, n'avait pas été adoptée définitivement. Les calculs de cette "
            "note s'appuient donc sur le droit en vigueur.")]
    H += [P(f"Ce diagnostic porte sur la <b>{config.EPCI_NOM}</b> (71 communes, environ 500 000 habitants, "
            "66 400 ha) et sur son PLUi, dont la dernière version a été approuvée le 4 mai 2026. Il répond "
            "à quatre questions, qui correspondent aux quatre premières étapes de la chaîne de traitement :")]
    H += puces(["Combien d'ENAF ont été consommés depuis 2011, où et pour quels usages ? Où en est la "
                "trajectoire de réduction de 50 % ?",
                "Comment l'occupation du sol a-t-elle évolué entre 2019 et 2022, au sens de l'artificialisation "
                "définie par le décret de 2023 ?",
                "Le réservoir foncier inscrit au PLUi (zones à urbaniser) est-il compatible avec l'enveloppe "
                "restante ?",
                f"Quel potentiel de densification existe dans le tissu urbain déjà constitué, sur deux communes "
                f"test ({' et '.join(communes)}) ?"])
    H += [P("La cinquième étape automatise l'ensemble : chaque traitement est un script Python paramétré, "
            "rejouable à chaque nouveau millésime et transposable à un autre territoire.")]

    # 2
    H += [P("2. Données mobilisées", "h1")]
    H += [P("Toutes les données sont publiques et diffusées sous Licence Ouverte Etalab 2.0 (ou licence "
            "équivalente). Elles sont téléchargées automatiquement par le script <i>00_telecharger_donnees.py</i>, "
            "puis découpées sur le périmètre de la Métropole et projetées en Lambert-93 (EPSG:2154).")]
    H += [tableau([
        ["Donnée", "Producteur", "Millésime", "Usage"],
        ["Consommation d'ENAF par commune (fichiers fonciers)", "Cerema", "Flux annuels 2011-2025, publication 2026", "Étape 1"],
        ["Population, ménages, emplois", "INSEE (via Cerema)", "2011, 2016, 2022", "Étape 1"],
        ["OCS GE 2.0 - Seine-Maritime", "IGN", "2019, 2022 et différentiel 2019-2022", "Étapes 2 à 4"],
        ["ADMIN EXPRESS COG (limites communales)", "IGN", "Édition en vigueur", "Toutes"],
        ["PLUi : zonage et prescriptions (standard CNIG)", "Métropole, via le Géoportail de l'Urbanisme", "Approuvé le 04/05/2026", "Étapes 3 et 4"],
        ["Registre parcellaire graphique", "ASP / IGN", "2024", "Étape 3"],
        ["Parcellaire Express (PCI)", "IGN / DGFiP", "Édition en vigueur", "Étape 4"],
        ["BD TOPO - bâtiments", "IGN", "Édition en vigueur", "Étape 4"],
    ], [5.6 * cm, 3.8 * cm, 4.6 * cm, 3 * cm])]
    H += [PageBreak()]

    # 3
    H += [P("3. Consommation d'espaces naturels, agricoles et forestiers", "h1")]
    H += [P("<b>Méthode.</b> Le Cerema mesure la consommation d'ENAF à partir des fichiers fonciers : une "
            "parcelle est consommée l'année où elle passe d'un usage naturel, agricole ou forestier à un "
            "usage urbanisé (habitat, activité, infrastructure). Les flux annuels du 1er janvier de l'année n "
            "au 1er janvier n+1 sont sommés par période. L'enveloppe 2021-2031 est calculée ici à 50 % de la "
            "consommation 2011-2021 : c'est une <b>enveloppe indicative</b>, avant la territorialisation par "
            "le SRADDET de Normandie et le SCoT, qui peuvent la moduler.")]
    H += [encadre(f"<b>{fr(s1['conso_1121_ha'], 0, 'ha')}</b> ont été consommés entre 2011 et 2021, soit "
                  f"{fr(s1['moy_an_1121_ha'], 1, 'ha')} par an, dont {pct(s1['part_hab_1121'] * 100)} pour "
                  f"l'habitat et {pct(s1['part_act_1121'] * 100)} pour l'activité économique. Depuis 2021, le "
                  f"rythme a baissé de {pct(abs(s1['evol_rythme_pct']))} ({fr(s1['moy_an_2125_ha'], 1, 'ha')} "
                  f"par an), moins que les 50 % visés : <b>{pct(s1['part_enveloppe'] * 100)} de l'enveloppe "
                  f"indicative ({fr(s1['enveloppe_zan_ha'], 0, 'ha')}) étaient utilisés au 1er janvier 2025</b>, "
                  f"après 4 années sur 10. Au rythme 2021-2024, l'enveloppe serait épuisée {epuisement}.")]
    H += [Spacer(1, 8), figure(G / "G01_Consommation_annuelle_ENAF_2011-2024.png",
                               "Figure 1 - Consommation annuelle d'ENAF par destination. Le pic de 2019 "
                               "(121 ha) est dû pour l'essentiel à l'activité économique.")]
    H += [figure(G / "G02_Trajectoire_ZAN_2021-2031.png",
                 "Figure 2 - Consommation cumulée depuis 2021 comparée à une trajectoire linéaire de -50 %.")]
    H += [figure(F / "C01_Consommation_ENAF_2011-2021.png",
                 "Figure 3 - Planche C01 : consommation 2011-2021 par commune (cercles proportionnels, "
                 "couleur = destination dominante).")]
    H += [P("<b>Lecture cartographique.</b> Les valeurs absolues (hectares) sont représentées par des cercles "
            "proportionnels, et les rapports (taux d'évolution) par des aplats de couleur (planche C02), "
            "conformément aux règles de la sémiologie graphique. Les couleurs suivent les conventions de "
            "l'urbanisme (habitat rouge-orangé, activités violet, eau bleu) et ont été vérifiées par un "
            "contrôle automatique de la lisibilité pour les daltonismes (écart de couleur OKLab).")]
    H += [PageBreak()]

    # 4
    H += [P("4. Artificialisation des sols 2019-2022", "h1")]
    H += [P("<b>Méthode.</b> L'OCS GE décrit chaque portion du territoire par une couverture (bâti, surface "
            "revêtue, herbacé, forêt...) et un usage (résidentiel, agricole, transport...). Chaque polygone "
            "est classé artificialisé ou non selon la nomenclature annexée au <b>décret n° 2023-1096 du "
            "27 novembre 2023</b>, appliquée ici sans les seuils de surface :")]
    H += [tableau([
        ["Couverture OCS GE", "Usage", "Classement"],
        ["CS1.1.1.x - zones bâties ou revêtues", "Tous, sauf extraction (US1.3)", "Artificialisé"],
        ["CS1.1.2.x - matériaux minéraux ou composites", "Tous, sauf extraction (US1.3)", "Artificialisé"],
        ["CS2.2.x - formations herbacées", "Résidentiel, activités, transports, réseaux, chantiers, friches (US2 à US6.2)", "Artificialisé"],
        ["CS2.2.x - formations herbacées", "Agriculture, sylviculture, sans usage", "Non artificialisé"],
        ["CS2.1.x - formations ligneuses (forêts, haies...)", "Tous", "Non artificialisé"],
        ["CS1.2.x - sols nus, eau ; carrières (US1.3)", "Tous", "Non artificialisé"],
    ], [6 * cm, 7.5 * cm, 3.5 * cm])]
    H += [Spacer(1, 6), P("Les flux sont tirés du produit <b>différentiel 2019-2022</b> de l'IGN, plus fiable "
                          "qu'une comparaison directe des deux millésimes, qui ferait apparaître des écarts "
                          "dus aux seules corrections de géométrie.")]
    H += [encadre(f"En 2022, <b>{pct(s2['part_artif_2022'] * 100)}</b> du territoire est artificialisé "
                  f"({fr(s2['artif_2022_ha'], 0, 'ha')}). Entre 2019 et 2022, "
                  f"{fr(s2['artif_brute_ha'], 0, 'ha')} ont été artificialisés et "
                  f"{fr(s2['desartif_ha'], 0, 'ha')} désartificialisés, soit une <b>artificialisation nette "
                  f"de {fr(s2['artif_nette_ha'], 0, 'ha')}</b> en trois ans. Sur une période proche (flux 2019 "
                  f"à 2021), le Cerema mesure {fr(s2['conso_enaf_2019_2021_ha'], 0, 'ha')} de consommation "
                  "d'ENAF : les deux ordres de grandeur sont cohérents, mais les deux indicateurs ne "
                  "mesurent pas la même chose et ne doivent pas être additionnés ni comparés terme à terme.")]
    H += [Spacer(1, 8), figure(G / "G04_Origine_destination_artificialisation_2019-2022.png",
                               "Figure 4 - Origine (occupation 2019) et destination (usage 2022) des surfaces "
                               "artificialisées.")]
    H += [figure(F / "C04_Artificialisation_2019-2022.png",
                 "Figure 5 - Planche C04 : localisation de l'artificialisation et de la désartificialisation.")]
    H += [PageBreak()]

    # 5
    H += [P("5. Le PLUi face à la trajectoire ZAN", "h1")]
    H += [P("<b>Méthode.</b> Les 3 241 zones du règlement graphique (standard CNIG) sont regroupées en quatre "
            "familles (U, AU, A, N), puis croisées avec l'OCS GE 2022 et le RPG 2024. Pour les zones à "
            "urbaniser, la vocation (habitat, activités, loisirs) est déduite du code de zone (1AUB, 1AUX, "
            "2AU...). La surface non artificialisée des zones AU mesure le <b>réservoir de consommation "
            "future</b> inscrit dans le document.")]
    H += [encadre(f"Le PLUi compte <b>{fr(s3['au_total_ha'], 0, 'ha')} de zones à urbaniser</b>, dont "
                  f"{fr(s3['au_ouvertes_ha'], 0, 'ha')} ouvertes (1AU) et {fr(s3['au_fermees_ha'], 0, 'ha')} "
                  f"fermées (2AU). <b>{fr(s3['au_non_artif_ha'], 0, 'ha')} y sont encore non "
                  f"artificialisés</b>, dont {fr(s3['au_rpg_ha'], 0, 'ha')} de parcelles agricoles déclarées "
                  f"à la PAC. C'est {fr(s3['au_non_artif_ha'] / restant, 1)} fois l'enveloppe restante "
                  f"jusqu'en 2031 ({fr(restant, 0, 'ha')}). À l'inverse, les zones urbaines contiennent "
                  f"{fr(s3['u_non_artif_ha'], 0, 'ha')} non artificialisés (jardins, parcs, terrains libres), "
                  "dont une partie seulement est mobilisable sans nuire à la nature en ville.", BLEU_PALE)]
    H += [Spacer(1, 8), figure(G / "G05_Reservoir_AU_vs_enveloppe_ZAN.png",
                               "Figure 6 - Surfaces non artificialisées des zones AU comparées à l'enveloppe "
                               "restante.")]
    H += [figure(F / "C06_Reservoir_foncier_zones_AU.png",
                 "Figure 7 - Planche C06 : zones AU selon leur vocation et l'état des sols en 2022.")]
    H += [P("<b>Interprétation.</b> Toutes les zones AU ne seront pas urbanisées d'ici 2031 : les zones 2AU "
            "doivent d'abord être ouvertes par une évolution du PLUi, et une partie des zones 1AU a déjà été "
            "aménagée après 2022 (ZAC en cours). L'écart reste suffisamment important pour poser la question "
            "du phasage de l'ouverture à l'urbanisation et de la priorité donnée au renouvellement urbain.")]
    H += [PageBreak()]

    # 6
    H += [P("6. Gisements de densification", "h1")]
    H += [P(f"<b>Objectif.</b> L'article L.151-5 du code de l'urbanisme subordonne toute nouvelle consommation "
            f"d'ENAF dans un PLU(i) à une étude de densification des zones déjà urbanisées. Une méthode "
            f"automatisée de repérage a été testée sur {' et '.join(communes)}, deux communes périurbaines "
            "du plateau nord parmi les plus consommatrices d'ENAF depuis 2011.")]
    H += [tableau([
        ["Critère", "Règle appliquée"],
        ["Périmètre", "Parcelles situées à plus de 50 % en zone U à dominante habitat (UA, UB, UC, UD, UR)"],
        ["Bâti existant", f"BD TOPO, hors constructions légères et bâtiments de moins de {config.SURFACE_BATI_MIN_M2} m²"],
        ["Espace libre", f"Parcelle moins un recul de {config.TAMPON_BATI_M} m autour du bâti"],
        ["Contraintes du PLUi", "Exclusion des EBC, cœurs d'îlot, parcs, vergers et jardins protégés, "
                                "zones de risque de cavité souterraine, aléas forts, emplacements réservés d'infrastructure"],
        ["Forme du lot", f"Le terrain doit pouvoir contenir un carré de {config.LARGEUR_MIN_LOT_M} m de côté "
                         f"(ouverture morphologique) et mesurer au moins {config.SEUIL_DENT_CREUSE_M2} m²"],
        ["Accès", f"Contact d'au moins {config.FACADE_MIN_M} m avec la voie publique ou une voie de lotissement "
                  "(espace non cadastré ou parcelle à usage routier dans l'OCS GE)"],
        ["Typologie", f"Dent creuse : parcelle non bâtie. Grand tènement : plus de {fr(config.GRAND_TENEMENT_M2)} m² "
                      f"libres. Division parcellaire : parcelle bâtie de plus de {fr(config.SURFACE_MIN_DIVISION_M2)} m² "
                      f"avec une emprise au sol inférieure à {pct(config.SEUIL_EMPRISE_SOUS_OCC * 100)}"],
        ["Vigilance", "Terrains boisés à plus de 50 % ou situés dans une OAP : signalés, à arbitrer"],
        ["Programmation", f"{config.DENSITE_LOG_HA} logements/ha ; mobilisation à 10 ans : dents creuses "
                          f"{pct(config.TAUX_MOBILISATION['Dent creuse'] * 100)}, divisions "
                          f"{pct(config.TAUX_MOBILISATION['Division parcellaire'] * 100)}, grands tènements "
                          f"{pct(config.TAUX_MOBILISATION['Grand tènement'] * 100)} (hypothèses)"],
    ], [3.4 * cm, 13.6 * cm])]
    lignes = [["Commune", "Gisements", "Surface", "dont dents creuses", "dont divisions", "Logements bruts",
               "Mobilisables à 10 ans"]]
    for nom, s in s4.items():
        lignes.append([nom, s["nb_gisements"], fr(s["surface_ha"], 1, "ha"),
                       f"{s['nb_Dent creuse']} ({fr(s['ha_Dent creuse'], 1, 'ha')})",
                       f"{s['nb_Division parcellaire']} ({fr(s['ha_Division parcellaire'], 1, 'ha')})",
                       s["logements_bruts"], f"≈ {fr(s['logements_mobilisables'], 0)}"])
    H += [Spacer(1, 10), P("Résultats", "h2"),
          tableau(lignes, [3 * cm, 1.9 * cm, 1.9 * cm, 2.6 * cm, 2.6 * cm, 2.3 * cm, 2.7 * cm])]
    H += [Spacer(1, 6), P(f"Au total, <b>{tot_gis} terrains et {fr(tot_ha, 0, 'ha')}</b> sont mobilisables "
                          f"dans l'enveloppe urbaine, soit environ <b>{fr(tot_log, 0)} logements à 10 ans</b> "
                          "après prise en compte de la rétention foncière. Les divisions parcellaires "
                          "dominent : c'est la marque d'un tissu pavillonnaire à grandes parcelles, typique "
                          "du plateau nord.")]
    H += [P("Environ les trois quarts de cette surface étaient déjà artificialisés en 2022 (jardins, cours, "
            "stationnements) ; le reste est boisé ou agricole et pourrait compter comme consommation d'ENAF "
            "selon sa nature au cadastre, que seuls les fichiers fonciers détaillés permettent de vérifier.")]
    nom2 = communes[-1].replace(" ", "-")
    H += [figure(F / f"C08_Gisements_densification_{nom2}.png",
                 f"Figure 8 - Planche C08 : gisements repérés à {communes[-1]}.")]
    H += [PageBreak()]
    if s4b:
        H += section_divisions(s4b, F, G)

    # 7
    H += [P("7. Chaîne de traitement et mise à jour", "h1")]
    H += [P("Tout le diagnostic est produit par une chaîne de scripts Python (geopandas, GDAL/OGR, "
            "matplotlib), pilotée par un fichier de paramètres unique (<i>config.py</i>). Aucune "
            "manipulation manuelle n'est nécessaire entre la donnée source et le livrable final.")]
    H += [tableau([
        ["Script", "Rôle", "Sorties principales"],
        ["00_telecharger_donnees", "Téléchargement (WFS Géoplateforme, data.gouv.fr), découpage, reprojection", "Base de travail GeoPackage"],
        ["01_consommation_enaf", "Indicateurs ENAF, trajectoire ZAN", "C01, C02, G01 à G03"],
        ["02_evolution_ocsge", "Classement artificialisé / non artificialisé, flux 2019-2022", "C03, C04, G04"],
        ["03_plui_occupation", "Croisement zonage x OCS GE x RPG", "C05, C06, G05"],
        ["04_gisements_densification", "Repérage des gisements à la parcelle", "C07, C08"],
        ["04b_divisions_parcellaires", "Divisions observées 2018-2026 (cadastre)", "C09, G06, atlas des divisions"],
        ["05_livrables", "Exports SIG, classeur, atlas, carte web", "GPKG, GDB, XLSX, atlas PDF"],
        ["06_documents", "Note, fiche tutoriel, bordereau", "PDF"],
        ["run_all", "Exécution de toute la chaîne", "Journal d'exécution"],
        ["07_projet_qgis (QGIS)", "Projet QGIS : symbologie, thèmes, mises en page, atlas", "diagnostic_zan_rouen.qgz"],
        ["08_modeles_traitement (QGIS)", "Modèles du modeleur graphique", "2 fichiers .model3"],
    ], [4.4 * cm, 7.6 * cm, 5 * cm])]
    H += [Spacer(1, 8), P("<b>Mise à jour annuelle.</b> À chaque nouvelle publication du Cerema ou de l'IGN, "
                          "il suffit de remplacer les adresses de téléchargement dans <i>config.py</i> et de "
                          "relancer la chaîne :"),
          P("python scripts/run_all.py", "code"),
          P("<b>Transposition.</b> Changer le code SIREN de l'EPCI, le département et la liste des communes "
            "test suffit pour produire le même diagnostic sur un autre territoire. La procédure est détaillée "
            "dans la fiche tutoriel.")]

    # 8
    H += [P("8. Limites et précautions d'usage", "h1")]
    H += puces([
        "<b>Enveloppe indicative.</b> L'objectif de -50 % s'apprécie à l'échelle du document d'urbanisme, "
        "après territorialisation par le SRADDET et le SCoT. Les valeurs communales servent à repérer des "
        "dynamiques, pas à juger la conformité d'une commune.",
        "<b>Fichiers fonciers.</b> La consommation est datée par la mutation fiscale, avec un décalage possible "
        "sur le terrain. Une part de destination « inconnue » subsiste certaines années.",
        "<b>OCS GE.</b> Les seuils de surface du décret de 2023 ne sont pas appliqués : la mesure est un peu "
        "plus fine que la mesure réglementaire. Seuls deux millésimes existent, ce qui limite l'analyse "
        "tendancielle.",
        "<b>Zones AU.</b> L'état des sols date de 2022 : les opérations engagées depuis ne sont pas visibles.",
        "<b>Gisements.</b> Repérage automatique sans visite de terrain. La pente, les réseaux, les servitudes "
        "privées, la qualité écologique des jardins et la volonté des propriétaires ne sont pas connus. Les "
        "résultats doivent être confrontés au terrain et aux connaissances des communes.",
        "<b>Statut.</b> Étude indépendante réalisée à partir de données ouvertes. Elle n'engage ni la Métropole "
        "Rouen Normandie ni les producteurs de données.",
    ])
    # 9
    H += [P("9. Pistes de prolongement", "h1")]
    H += puces([
        "Remplacer l'OCS GE par le mode d'occupation des sols (MOS) de la Métropole, plus fin et plus ancien, "
        "pour remonter avant 2019.",
        "Étendre le repérage des gisements à l'ensemble des 71 communes et le valider avec les services "
        "communaux (atelier de terrain, retours sur la carte web).",
        "Croiser avec les fichiers fonciers à la parcelle (propriétaires publics, date de construction) pour "
        "qualifier la mutabilité.",
        "Intégrer les friches (Cartofriches, Cerema) au potentiel de renouvellement urbain.",
        "Publier les indicateurs sur un tableau de bord ArcGIS Online ou une page du géoportail métropolitain.",
    ])
    H += [PageBreak(), P("Annexe : liste des livrables", "h1"), P("Voir le bordereau de livraison joint "
          "(01_Documents/00_Bordereau_de_livraison.pdf), qui détaille chaque fichier, son format et son usage.")]
    construire(DOSSIER_DOC / "01_Note_methodologique.pdf", "Note méthodologique - diagnostic foncier ZAN",
               couverture("Diagnostic foncier ZAN\net PLUi", "Note méthodologique et résultats",
                          [("Territoire", config.EPCI_NOM), ("Réalisation", config.AUTEUR),
                           ("Date", AUJOURDHUI), ("Version", VERSION),
                           ("Données", "Cerema, IGN, Géoportail de l'Urbanisme, ASP, INSEE")]), H)


# --- Fiche tutoriel ----------------------------------------------------------------------------------
def fiche_tutoriel():
    H = [P("Fiche 1 - Mettre à jour le diagnostic", "h1"),
         P("<b>Quand ?</b> Chaque année, à la publication du nouveau millésime de consommation d'ENAF par le "
           "Cerema (en général au printemps), et à chaque livraison d'un millésime OCS GE par l'IGN."),
         P("1. Installer l'environnement (une seule fois)", "h2"),
         P("python -m venv .venv<br/>.venv\\Scripts\\activate<br/>pip install -r requirements.txt", "code"),
         P("2. Mettre à jour les sources", "h2"),
         P("Ouvrir <i>scripts/config.py</i> et remplacer l'adresse <i>CEREMA_CSV</i> (page data.gouv.fr du jeu "
           "« Consommation d'espaces naturels, agricoles et forestiers ») et, le cas échéant, les noms des "
           "millésimes OCS GE (rubrique <i>OCSGE</i>). Supprimer le dossier <i>data/</i> pour forcer un "
           "nouveau téléchargement."),
         P("3. Relancer la chaîne", "h2"),
         P("python scripts/run_all.py", "code"),
         P("Pour ne rejouer qu'une partie, par exemple à partir des livrables :"),
         P("python scripts/run_all.py --depuis 6", "code"),
         P("4. Contrôler", "h2")]
    H += puces(["Lire le journal : chaque étape affiche ses chiffres clés et le nombre d'entités produites.",
                "Comparer la consommation 2011-2021 avec la valeur du portail de l'artificialisation "
                "(artificialisation.developpement-durable.gouv.fr) : l'écart doit être nul.",
                "Ouvrir les planches PNG et vérifier les étiquettes et la légende."])
    H += [P("Fiche 2 - Calculer la consommation d'ENAF d'un secteur", "h1"),
          P("Cas d'usage : un agent ou un bureau d'études souhaite connaître la consommation d'ENAF d'un "
            "périmètre de projet ou d'un groupe de communes. Deux méthodes équivalentes :"),
          P("Dans QGIS", "h2")]
    H += puces(["Ouvrir <i>02_Donnees_SIG/diagnostic_zan_rouen.gpkg</i> et ajouter la couche "
                "<i>communes_indicateurs</i>.",
                "Sélectionner les communes du secteur (sélection manuelle ou <i>Sélection par localisation</i> "
                "avec le périmètre du projet).",
                "Boîte à outils de traitements : <i>Statistiques basiques pour les champs</i> sur le champ "
                "<i>conso_1121_ha</i> (cocher « entités sélectionnées uniquement ») : la somme donne la "
                "consommation 2011-2021 du secteur.",
                "Pour un périmètre infracommunal, utiliser la couche <i>ocsge_flux_2019_2022</i> et l'outil "
                "<i>Intersection</i>, puis la calculatrice de champs : <i>$area / 10000</i>."])
    H += [P("Dans ArcGIS Pro", "h2")]
    H += puces(["Ajouter <i>02_Donnees_SIG/diagnostic_zan_rouen.gdb</i> au projet (même contenu que le "
                "GeoPackage).",
                "Sélectionner les communes (<i>Select By Location</i> avec le périmètre du projet).",
                "Outil <i>Summary Statistics</i> : champ <i>conso_1121_ha</i>, statistique SUM.",
                "Pour un périmètre infracommunal : <i>Tabulate Intersection</i> entre le périmètre et la couche "
                "<i>ocsge_flux_2019_2022</i>, champ de classe <i>type_flux</i>."])
    H += [P("Fiche 3 - Utiliser le projet QGIS, l'atlas et les modèles", "h1")]
    H += puces(["Ouvrir <i>02_Donnees_SIG/diagnostic_zan_rouen.qgz</i>. Les thèmes de carte (bouton « Gérer "
                "les thèmes » du panneau Couches) affichent les couches de chaque planche.",
                "<i>Projet > Mises en page</i> : 4 planches A3 prêtes à imprimer et l'<b>atlas communal</b>. "
                "Dans l'atlas, activer l'aperçu (barre Atlas), parcourir les communes, puis "
                "<i>Exporter l'atlas en PDF</i>.",
                "Boîte à outils de traitements > <i>Modèles du projet</i> : "
                "<b>Bilan d'artificialisation d'un secteur</b> (dessiner ou choisir un périmètre, résultat en "
                "hectares par type de flux) et <b>Espaces libres constructibles en zone U</b> (recul, largeur de "
                "lot et surface minimale réglables). Clic droit > <i>Éditer le modèle</i> pour ouvrir le "
                "modeleur graphique et voir l'enchaînement des traitements.",
                "Les modèles existent aussi en fichiers <i>.model3</i> dans <i>02_Donnees_SIG/modeles/</i>."])
    H += [Spacer(1, 6), encadre("<b>Bon réflexe.</b> Toujours indiquer la source, le millésime et la "
                                "définition utilisée (consommation d'ENAF au sens des fichiers fonciers ou "
                                "artificialisation au sens de l'OCS GE) : les deux chiffres ne sont pas "
                                "interchangeables. Le dictionnaire des données (feuille « Dictionnaire » du "
                                "classeur) décrit chaque champ.")]
    construire(DOSSIER_DOC / "02_Fiche_tutoriel.pdf", "Fiche tutoriel - outils et données SIG",
               couverture("Fiches tutoriel", "Mise à jour · Consommation d'ENAF · Projet QGIS et modèles",
                          [("Public", "Agents et prestataires utilisateurs des données"),
                           ("Réalisation", config.AUTEUR), ("Date", AUJOURDHUI)]), H)


# --- Bordereau de livraison ---------------------------------------------------------------------------
def bordereau():
    L = config.LIVRABLES
    lignes = [["N°", "Fichier ou dossier", "Format", "Contenu et usage"]]
    entrees = [
        ("01_Documents/01_Note_methodologique.pdf", "PDF", "Contexte, méthodes, résultats, limites"),
        ("01_Documents/02_Fiche_tutoriel.pdf", "PDF", "Mise à jour de la chaîne ; calculs dans QGIS et ArcGIS Pro"),
        ("02_Donnees_SIG/diagnostic_zan_rouen.gpkg", "GeoPackage", "11 couches livrées, Lambert-93 (QGIS)"),
        ("02_Donnees_SIG/diagnostic_zan_rouen.gdb", "Géodatabase fichier", "Mêmes couches pour ArcGIS Pro"),
        ("02_Donnees_SIG/diagnostic_zan_rouen.qgz", "Projet QGIS",
         "Couches symbolisées, 6 thèmes, 4 mises en page A3, atlas communal A4, 2 modèles intégrés"),
        ("02_Donnees_SIG/modeles/", "Modèles QGIS (.model3)",
         "Modeleur graphique : bilan d'artificialisation d'un secteur ; espaces libres en zone U"),
        ("02_Donnees_SIG/dictionnaire_des_donnees.csv", "CSV", "Description de chaque champ"),
        ("03_Planches_cartographiques/C01 à C09", "PDF + PNG (A3)", "9 planches thématiques imprimables"),
        ("04_Graphiques/G01 à G06", "PDF + PNG", "Graphiques d'analyse"),
        ("05_Tableaux/Indicateurs_diagnostic_ZAN_Rouen.xlsx", "Excel", "Indicateurs par commune, zones AU, gisements"),
        ("06_Atlas_communal/Atlas_communal_ZAN_Metropole_Rouen.pdf", "PDF (A4)", "Une page par commune (71)"),
        ("07_Atlas_divisions/Atlas_divisions_parcellaires_Metropole_Rouen.pdf", "PDF (A4)",
         "Atlas séparé des divisions parcellaires 2018-2026"),
        ("docs/index.html", "Page web", "Carte interactive (GitHub Pages)"),
        ("scripts/", "Python", "Chaîne de traitement complète et reproductible"),
    ]
    for i, (f, fmt, desc) in enumerate(entrees, start=1):
        chemin = config.ROOT / f if f.startswith(("docs", "scripts")) else L / f.split(" ")[0]
        present = "" if chemin.exists() or " à " in f else " (à générer)"
        lignes.append([str(i), f + present, fmt, desc])
    H = [P("Bordereau de livraison", "h1"),
         tableau([["Objet", "Diagnostic foncier ZAN et PLUi - " + config.EPCI_NOM],
                  ["Nature", "Projet personnel de démonstration (candidature), à partir de données ouvertes"],
                  ["Réalisation", config.AUTEUR], ["Date de livraison", date.today().strftime("%d/%m/%Y")],
                  ["Version", VERSION], ["Système de coordonnées", "RGF93 / Lambert-93 (EPSG:2154)"]],
                 [4.5 * cm, 12.5 * cm], entete=False),
         Spacer(1, 14), P("Contenu de la livraison", "h2"),
         tableau(lignes, [0.8 * cm, 7.4 * cm, 3 * cm, 5.8 * cm]),
         Spacer(1, 14), P("Contrôles réalisés avant livraison", "h2")]
    H += puces(["Totaux de consommation d'ENAF identiques à la source Cerema (somme des 71 communes).",
                "Somme des destinations égale au total pour chaque année (contrôle automatique).",
                "Géométries valides, type homogène MultiPolygon, projection Lambert-93 sur toutes les couches.",
                "Ouverture des données dans QGIS ; format géodatabase lisible par ArcGIS Pro.",
                "Relecture visuelle de chaque planche (étiquettes, légende, échelle, sources).",
                "Exécution complète de la chaîne depuis un dossier vide."])
    construire(DOSSIER_DOC / "00_Bordereau_de_livraison.pdf", "Bordereau de livraison",
               couverture("Bordereau\nde livraison", "Diagnostic foncier ZAN et PLUi",
                          [("Territoire", config.EPCI_NOM), ("Réalisation", config.AUTEUR),
                           ("Date", AUJOURDHUI), ("Version", VERSION)]), H)


def main():
    log("Étape 6 - Documents")
    DOSSIER_DOC.mkdir(parents=True, exist_ok=True)
    s = [json.loads((config.INTERIM / f"synthese_etape{k}.json").read_text(encoding="utf-8")) for k in (1, 2, 3, 4)]
    f4b = config.INTERIM / "synthese_etape4b.json"
    s4b = json.loads(f4b.read_text(encoding="utf-8")) if f4b.exists() else None
    note_methodologique(*s, s4b=s4b)
    fiche_tutoriel()
    bordereau()
    log("Documents produits")


if __name__ == "__main__":
    main()
