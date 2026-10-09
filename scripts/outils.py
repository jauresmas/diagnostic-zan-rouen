"""Fonctions communes : accès WFS Géoplateforme, lecture/écriture de la base."""
import time

import geopandas as gpd
import pandas as pd
import requests

import config

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "diagnostic-zan-rouen (projet portfolio)"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wfs(typename, cql=None, bbox=None, page=5000, sort=None):
    """Télécharge une couche WFS de la Géoplateforme IGN, page par page.

    cql  : filtre CQL (ex. "partition='DU_200023414'")
    bbox : (xmin, ymin, xmax, ymax) en Lambert-93, incompatible avec cql
    """
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "outputFormat": "application/json",
        "srsName": config.CRS,
        "count": page,
    }
    if cql:
        params["CQL_FILTER"] = cql
    if bbox is not None:
        params["BBOX"] = ",".join(str(round(v, 1)) for v in bbox) + f",{config.CRS}"
    if sort:
        params["sortBy"] = sort

    morceaux, debut = [], 0
    while True:
        params["startIndex"] = debut
        for essai in range(4):
            try:
                r = SESSION.get(config.WFS, params=params, timeout=180)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as err:
                if essai == 3:
                    raise
                log(f"  nouvel essai WFS ({err.__class__.__name__})")
                time.sleep(5 * (essai + 1))
        feats = data.get("features", [])
        if not feats:
            break
        morceaux.append(gpd.GeoDataFrame.from_features(feats, crs=config.CRS))
        debut += len(feats)
        if len(feats) < page:
            break
    if not morceaux:
        return gpd.GeoDataFrame(geometry=[], crs=config.CRS)
    return gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True), crs=config.CRS)


def lire(couche, **kw):
    return gpd.read_file(config.GPKG, layer=couche, **kw)


def ecrire(gdf, couche):
    config.GPKG.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(config.GPKG, layer=couche, driver="GPKG", engine="pyogrio")
    log(f"  -> {couche} : {len(gdf)} entités")


def ha(m2):
    return m2 / 10_000


def couches():
    import pyogrio
    return {nom for nom, _ in pyogrio.list_layers(config.GPKG)}


def fond_eau():
    """Surfaces en eau (Seine et grands plans d'eau) tirées de l'OCS GE 2022."""
    if "fond_eau" in couches():
        return lire("fond_eau")
    ocs = lire("ocsge_2022_occupation_sol", where="code_cs = 'CS1.2.2'")
    eau = ocs[["geometry"]].dissolve().explode(index_parts=False)
    eau = eau[eau.area > 20_000].reset_index(drop=True)
    ecrire(eau, "fond_eau")
    return eau
