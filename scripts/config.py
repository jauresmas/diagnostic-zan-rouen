"""Paramètres du diagnostic foncier ZAN.

Tout le traitement est piloté depuis ce fichier : pour appliquer la chaîne
à un autre EPCI, il suffit de changer EPCI_SIREN, DEPARTEMENT, les URL OCS GE
et la liste des communes étudiées pour la densification.
"""
from pathlib import Path

# --- Arborescence -----------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
LIVRABLES = ROOT / "livrables"
DOCS = ROOT / "docs"
GPKG = INTERIM / "diagnostic_zan.gpkg"  # base de travail unique

# --- Territoire -------------------------------------------------------------
EPCI_SIREN = "200023414"
EPCI_NOM = "Métropole Rouen Normandie"
DEPARTEMENT = "76"
CRS = "EPSG:2154"  # Lambert-93

# --- Cadre ZAN (loi Climat et Résilience, art. 191) --------------------------
PERIODE_REF = (2011, 2021)      # décennie de référence
PERIODE_ZAN = (2021, 2031)      # première tranche : -50 %
TAUX_REDUCTION = 0.50

# --- Sources ----------------------------------------------------------------
WFS = "https://data.geopf.fr/wfs/ows"
CEREMA_CSV = (
    "https://static.data.gouv.fr/resources/"
    "consommation-despaces-naturels-agricoles-et-forestiers-du-1er-janvier-2011-au-1er-janvier-2025/"
    "20260724-142909/conso-com.csv"
)
_OCSGE_DL = "https://data.geopf.fr/telechargement/download/OCSGE"
OCSGE = {
    2019: "OCS-GE_2-0__GPKG_LAMB93_D076_2019-01-01",
    2022: "OCS-GE_2-0__GPKG_LAMB93_D076_2022-01-01",
    "diff": "OCS-GE_2-0_DIFF-2019-2022_GPKG_LAMB93_D076_2025-06-12",
}
OCSGE_URL = {k: f"{_OCSGE_DL}/{v}/{v}.7z" for k, v in OCSGE.items()}

# Géoportail de l'Urbanisme : partition du PLUi de la Métropole
GPU_PARTITION = f"DU_{EPCI_SIREN}"

# Registre parcellaire graphique (déclarations PAC)
RPG_COUCHE = "RPG.2024:parcelles_graphiques"

# --- Étude de densification -------------------------------------------------
# Communes retenues pour le repérage des gisements (choisies à l'étape 1 :
# communes périurbaines du plateau nord, dans le top 3 de la consommation
# 2011-2021 et qui continuent à consommer sur 2021-2025, surtout pour l'habitat).
COMMUNES_DENSIFICATION = {
    "76377": "Isneauville",
    "76108": "Bois-Guillaume",
}
SEUIL_DENT_CREUSE_M2 = 400      # surface libre minimale pour un lot à bâtir
SEUIL_EMPRISE_SOUS_OCC = 0.15   # parcelle bâtie « sous-occupée » si emprise < 15 %
SURFACE_MIN_DIVISION_M2 = 1200  # parcelle bâtie divisible au-delà de ce seuil
TAMPON_BATI_M = 5               # recul autour du bâti existant (m)
LARGEUR_MIN_LOT_M = 15          # un lot doit pouvoir contenir un carré de 15 m de côté
FACADE_MIN_M = 4                # contact minimal avec la voie publique (accès)
SURFACE_BATI_MIN_M2 = 20        # en dessous : abri, annexe légère (ignorés)
GRAND_TENEMENT_M2 = 5000        # au-delà : relève d'une OAP plutôt que du diffus

# Hypothèses de programmation (à ajuster selon le SCoT et les OAP)
DENSITE_LOG_HA = 20             # logements / ha en densification diffuse périurbaine
TAUX_MOBILISATION = {           # part mobilisable à 10 ans (rétention foncière)
    "Dent creuse": 0.50,            # hypothèse
    "Division parcellaire": 0.12,   # observé : 10-12 % des grandes parcelles U habitat divisées
                                    # en 10 ans (étape 4 bis, Isneauville et Bois-Guillaume)
    "Grand tènement": 0.70,         # hypothèse
}
# Extension du repérage à toutes les communes (cartes détaillées C07/C08 : communes test)
DENSIFICATION_METROPOLE = True
SEUIL_TISSU_DENSE_HAB_HA = 20   # au-delà : centre urbain dense, méthode moins adaptée (avertissement)
CADASTRE_GISEMENTS = "2026-09-01"  # millésime Etalab utilisé pour le repérage

# Prescriptions du PLUi qui rendent un terrain non mobilisable
PRESCRIPTIONS_EXCLUANTES = {
    "01": None,  # espace boisé classé : toutes
    "02": ("cavité", "aléa fort"),  # risques : cavités souterraines, aléa fort
    "07": ("Coeur d'îlot", "Parc à préserver", "Jardins familiaux", "Verger",
           "Espace paysager", "Corridor"),  # patrimoine paysager (L151-19/23)
    "05": ("voie", "voirie", "chemin", "bassin", "cimetière", "équipement", "pelouses",
           "talus", "espace naturel", "trottoir", "sente", "carrefour", "berge"),
}

# --- Divisions parcellaires observées (étape 4 bis) ---------------------------
# Comparaison de deux millésimes du cadastre Etalab (PCI vecteur, trimestriel depuis 2017)
CADASTRE_ETALAB = "https://cadastre.data.gouv.fr/data/etalab-cadastre"
CADASTRE_MILLESIMES = ("2018-01-02", "2026-09-01")
COUVERTURE_MIN_DIVISION = 0.90   # part de la parcelle mère couverte par ses nouvelles parcelles
SEUIL_REMANIEMENT = 0.50         # section exclue si plus de 50 % de ses parcelles changent de numéro
SEUIL_ATLAS_DIVISIONS = 5        # une page d'atlas par commune ayant au moins 5 divisions

# --- Mise en page -------------------------------------------------------------
AUTEUR = "Jaurès DAA-HINGBANON"
