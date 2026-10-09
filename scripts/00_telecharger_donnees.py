"""Étape 0 - Collecte des données sources et découpage sur le territoire.

Sources (toutes en licence ouverte) :
  - IGN ADMIN EXPRESS COG : limites communales (WFS Géoplateforme)
  - Cerema : consommation d'ENAF 2011-2025 par commune (data.gouv.fr)
  - IGN OCS GE 2.0 : millésimes 2019 et 2022 + différentiel (Seine-Maritime)
  - Géoportail de l'Urbanisme : zonage du PLUi en vigueur
  - ASP/IGN : Registre parcellaire graphique 2024
  - IGN : Parcellaire Express et BD TOPO (communes de l'étude de densification)
"""
import shutil

import geopandas as gpd
import py7zr
import pyogrio

import config
from outils import SESSION, ecrire, log, wfs


def telecharger(url, dest):
    if dest.exists():
        log(f"  déjà présent : {dest.name}")
        return dest
    log(f"  téléchargement : {dest.name}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with SESSION.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        r.raw.decode_content = True  # décompresse si le serveur envoie du gzip
        with open(tmp, "wb") as f:
            shutil.copyfileobj(r.raw, f, length=1 << 20)
    tmp.rename(dest)
    return dest


def communes():
    log("Communes de l'EPCI (ADMIN EXPRESS COG)")
    gdf = wfs(
        "ADMINEXPRESS-COG.LATEST:commune",
        cql=f"codes_siren_des_epci LIKE '%{config.EPCI_SIREN}%'",
    )
    gdf = gdf[["code_insee", "nom_officiel", "population", "geometry"]].rename(
        columns={"nom_officiel": "nom", "population": "pop_legale"}
    )
    gdf["surface_ha"] = gdf.area / 10_000
    ecrire(gdf.sort_values("code_insee"), "communes")
    perim = gdf.dissolve()[["geometry"]]
    perim["nom"] = config.EPCI_NOM
    ecrire(perim, "perimetre")
    return gdf


def ocsge(com):
    log("OCS GE (IGN) : extraction et découpage")
    dossier = config.RAW / "ocsge"
    dossier.mkdir(parents=True, exist_ok=True)
    bbox = tuple(com.total_bounds)
    for cle, nom in config.OCSGE.items():
        archive = telecharger(config.OCSGE_URL[cle], config.RAW / f"{nom}.7z")
        cible = dossier / nom
        if not cible.exists():
            log(f"  décompression {archive.name}")
            with py7zr.SevenZipFile(archive) as z:
                z.extractall(cible)
        gpkgs = sorted(cible.rglob("*.gpkg"))
        for g in gpkgs:
            for couche, _ in pyogrio.list_layers(g):
                log(f"  {g.name} / {couche}")
                gdf = gpd.read_file(g, layer=couche, bbox=bbox, engine="pyogrio")
                if gdf.empty or gdf.geometry.isna().all():
                    continue
                gdf = gdf.to_crs(config.CRS)
                # rattachement communal : découpe par les limites communales
                gdf = gpd.overlay(
                    gdf, com[["code_insee", "geometry"]], how="intersection",
                    keep_geom_type=True,
                )
                gdf.columns = [c.lower() for c in gdf.columns]
                nom_couche = "ocsge_diff_2019_2022" if cle == "diff" else f"ocsge_{cle}_{couche.lower()}"
                ecrire(gdf, nom_couche)


def plui(com):
    log("Zonage du PLUi (Géoportail de l'Urbanisme)")
    docs = wfs("wfs_du:doc_urba", cql=f"partition='{config.GPU_PARTITION}'")
    docs = docs.sort_values("datappro", ascending=False)
    doc = docs.iloc[0]
    log(f"  document retenu : {doc['idurba']} (approuvé le {doc['datappro']})")
    zones = wfs(
        "wfs_du:zone_urba",
        cql=f"gpu_doc_id='{doc['gpu_doc_id']}'",
        sort="gid",
    )
    if zones.empty:  # repli : toutes les zones de la partition
        zones = wfs("wfs_du:zone_urba", cql=f"partition='{config.GPU_PARTITION}'", sort="gid")
    zones = zones[["libelle", "libelong", "typezone", "idurba", "urlfic", "geometry"]]
    zones = gpd.overlay(zones, com[["code_insee", "geometry"]], how="intersection",
                        keep_geom_type=True)
    ecrire(zones, "plui_zonage")


def rpg(com):
    log("Registre parcellaire graphique 2024")
    gdf = wfs(config.RPG_COUCHE, bbox=com.total_bounds, sort="id_parcel")
    gdf = gpd.overlay(gdf, com[["code_insee", "geometry"]], how="intersection",
                      keep_geom_type=True)
    ecrire(gdf, "rpg_2024")


def densification(com):
    log("Cadastre et bâti des communes étudiées")
    parcelles, batis = [], []
    for insee, nom in config.COMMUNES_DENSIFICATION.items():
        log(f"  {nom} ({insee})")
        p = wfs("CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle",
                cql=f"code_insee='{insee}'", sort="gid")
        p["code_insee"] = insee
        parcelles.append(p[["idu", "section", "numero", "contenance", "code_insee", "geometry"]])
        zone = com[com.code_insee == insee]
        b = wfs("BDTOPO_V3:batiment", bbox=zone.total_bounds, sort="cleabs")
        b = gpd.clip(b, zone)
        b["code_insee"] = insee
        batis.append(b[["cleabs", "nature", "usage_1", "construction_legere",
                        "nombre_de_logements", "hauteur", "code_insee", "geometry"]])
    ecrire(gpd.pd.concat(parcelles, ignore_index=True), "cadastre_parcelles")
    ecrire(gpd.pd.concat(batis, ignore_index=True), "bdtopo_batiments")


def main():
    config.RAW.mkdir(parents=True, exist_ok=True)
    telecharger(config.CEREMA_CSV, config.RAW / "conso_com.csv")
    com = communes()
    plui(com)
    rpg(com)
    densification(com)
    ocsge(com)
    log("Collecte terminée")


if __name__ == "__main__":
    main()
