"""Étape 4 - Repérage des gisements fonciers de densification (zones U à vocation habitat).

Méthode (inspirée des études de densification prévues à l'art. L.151-5 du
Code de l'urbanisme, sans visite de terrain) :
  1. Parcelles cadastrales situées majoritairement en zone U à dominante habitat.
  2. Emprise du bâti BD TOPO (hors constructions légères et annexes < 20 m²).
  3. Espace libre = parcelle - tampon de 5 m autour du bâti - prescriptions excluantes
     du PLUi (EBC, patrimoine paysager, risques de cavités et aléas forts, emplacements
     réservés d'infrastructures).
  4. « Ouverture » morphologique de 7,5 m : on ne garde que les espaces où un carré
     de 15 m de côté peut s'inscrire (forme de lot constructible).
  5. Typologie : dent creuse (parcelle non bâtie), grand tènement (> 5 000 m² non bâtis),
     division parcellaire (parcelle bâtie > 1 200 m², emprise < 15 %).
  6. Potentiel de logements = surface x densité, puis pondération par un taux de
     mobilisation à 10 ans (rétention foncière). Hypothèses dans config.py.
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

import cartes as C
import config
from outils import couches, ecrire, lire, log, wfs

TYPES = {
    "Dent creuse": "#b8262b",
    "Grand tènement": "#6e1414",
    "Division parcellaire": "#f0a04b",
}
PREFIXES_HABITAT = ("UA", "UB", "UC", "UD", "UR")


def prescriptions(zone):
    if "plui_prescriptions_etude" in couches():
        return lire("plui_prescriptions_etude")
    b = zone.total_bounds
    log("  téléchargement des prescriptions surfaciques du PLUi")
    docs = lire("plui_zonage").idurba.iloc[0]
    p = wfs("wfs_du:prescription_surf",
            cql=f"idurba='{docs}' AND BBOX(the_geom,{b[0]},{b[1]},{b[2]},{b[3]},'EPSG:2154')",
            sort="gid")
    p = p[["typepsc", "stypepsc", "libelle", "geometry"]]
    p["geometry"] = p.geometry.make_valid()
    ecrire(p, "plui_prescriptions_etude")
    return p


def est_excluante(row):
    regle = config.PRESCRIPTIONS_EXCLUANTES.get(row.typepsc, False)
    if regle is False:
        return False
    if regle is None:
        return True
    lib = str(row.libelle).lower()
    return any(m.lower() in lib for m in regle)


def ouverture(geom, demi_largeur):
    """Supprime les parties trop étroites pour accueillir un lot."""
    if geom is None or geom.is_empty:
        return geom
    return geom.buffer(-demi_largeur, join_style="mitre").buffer(demi_largeur, join_style="mitre").intersection(geom)


def domaine_public(geom_commune, parcelles, routes_ocs):
    """Réseau de desserte : espace non cadastré (voirie publique) + parcelles cadastrées
    occupées à plus de 50 % par un usage routier dans l'OCS GE (voies privées de
    lotissement). Une ouverture de 1,5 m retire les interstices de numérisation."""
    vide = geom_commune.difference(shapely.union_all(parcelles.geometry.values))
    x = gpd.overlay(parcelles[["idu", "geometry"]], routes_ocs[["geometry"]], how="intersection",
                    keep_geom_type=True)
    part = (x.area.groupby(x.idu).sum() / parcelles.set_index("idu").area).fillna(0)
    voies_privees = parcelles[parcelles.idu.map(part).fillna(0) > 0.5]
    return shapely.union_all([vide, *voies_privees.geometry.values]).buffer(-1.5).buffer(1.5)


def analyser_commune(insee, nom, geom_commune, parc, zones, bati, excl, oap, ocs):
    log(f"  {nom}")
    p = parc[parc.code_insee == insee][["idu", "contenance", "geometry"]].copy()
    p["geometry"] = p.geometry.make_valid()
    p["surface_m2"] = p.area
    voirie = domaine_public(geom_commune, p, ocs[(ocs.code_insee == insee) & (ocs.code_us == "US4.1.1")])
    u = zones[(zones.code_insee == insee) & (zones.famille == "U")
              & zones.libelle.str.startswith(PREFIXES_HABITAT) & ~zones.libelle.str.startswith("URX")]
    x = gpd.overlay(p[["idu", "geometry"]], u[["libelle", "geometry"]], how="intersection", keep_geom_type=True)
    x["a"] = x.area
    part_u = x.groupby("idu").a.sum() / p.set_index("idu").surface_m2
    zone_maj = x.sort_values("a").groupby("idu").libelle.last()
    p = p[p.idu.map(part_u).fillna(0) >= 0.5].copy()
    p["zone_plui"] = p.idu.map(zone_maj)

    b = bati[bati.code_insee == insee]
    xb = gpd.overlay(p[["idu", "geometry"]], b[["geometry"]], how="intersection", keep_geom_type=True)
    emprise = (xb.area).groupby(xb.idu).sum()
    p["emprise_bati_m2"] = p.idu.map(emprise).fillna(0)
    p["coef_emprise"] = p.emprise_bati_m2 / p.surface_m2

    # espace libre
    tampon = shapely.union_all(b.geometry.buffer(config.TAMPON_BATI_M).values)
    contraintes = shapely.union_all(excl.geometry.values) if len(excl) else shapely.Polygon()
    libre = p.geometry.difference(tampon).difference(contraintes)
    libre = libre.apply(lambda g: ouverture(g, config.LARGEUR_MIN_LOT_M / 2))
    p["geom_libre"] = libre
    p["surface_libre_m2"] = gpd.GeoSeries(libre, crs=config.CRS).area.fillna(0)
    # accès : l'espace libre doit toucher la voie publique sur au moins 4 m
    # (largeur d'un accès carrossable) ; sinon le terrain est enclavé
    contact = gpd.GeoSeries(libre, crs=config.CRS).buffer(2).intersection(voirie).area / 2
    p["facade_voie_m"] = contact.fillna(0).round(1)
    accessible = p.facade_voie_m >= config.FACADE_MIN_M

    non_bati = p.emprise_bati_m2 < config.SURFACE_BATI_MIN_M2
    p["enclave"] = (p.surface_libre_m2 >= config.SEUIL_DENT_CREUSE_M2) & ~accessible
    cond_dc = non_bati & accessible & (p.surface_libre_m2 >= config.SEUIL_DENT_CREUSE_M2)
    cond_gt = cond_dc & (p.surface_libre_m2 >= config.GRAND_TENEMENT_M2)
    cond_div = (~non_bati & accessible & (p.surface_m2 >= config.SURFACE_MIN_DIVISION_M2)
                & (p.coef_emprise < config.SEUIL_EMPRISE_SOUS_OCC)
                & (p.surface_libre_m2 >= config.SEUIL_DENT_CREUSE_M2))
    p["type_gisement"] = np.select([cond_gt, cond_dc, cond_div],
                                   ["Grand tènement", "Dent creuse", "Division parcellaire"], default="")
    g = p[p.type_gisement != ""].copy()
    g = gpd.GeoDataFrame(g.drop(columns="geometry").rename(columns={"geom_libre": "geometry"}),
                         geometry="geometry", crs=config.CRS)
    g["code_insee"], g["commune"] = insee, nom

    # boisement (OCS GE) et OAP : signalés, à arbitrer
    o = ocs[ocs.code_insee == insee]
    xo = gpd.overlay(g[["idu", "geometry"]], o[o.code_cs.str.startswith("CS2.1")][["geometry"]],
                     how="intersection", keep_geom_type=True)
    g["part_boisee"] = g.idu.map(xo.area.groupby(xo.idu).sum()).fillna(0) / g.area
    g["dans_oap"] = g.geometry.intersects(shapely.union_all(oap.geometry.values)) if len(oap) else False
    g["vigilance"] = np.where(g.part_boisee > 0.5, "Terrain boisé à plus de 50 % : à arbitrer",
                              np.where(g.dans_oap, "Dans le périmètre d'une OAP", ""))
    g["logements_bruts"] = np.maximum(1, np.floor(g.surface_libre_m2 / 1e4 * config.DENSITE_LOG_HA)).astype(int)
    g["taux_mobilisation"] = g.type_gisement.map(config.TAUX_MOBILISATION)
    g["logements_mobilisables"] = g.logements_bruts * g.taux_mobilisation
    p_out = p.drop(columns="geom_libre")
    p_out["code_insee"], p_out["commune"] = insee, nom
    return g, p_out


# --- Carte communale -------------------------------------------------------------
def carte_commune(insee, nom, g, parc_u, com, zones, bati, excl, synth_c):
    fig, ax, axp = C.planche(f"Gisements fonciers de densification : {nom}",
                             "Repérage automatisé dans les zones urbaines à dominante habitat du PLUi")
    zone = com[com.code_insee == insee]
    xmin, ymin, xmax, ymax = zone.total_bounds
    pad = 250
    # cadre au ratio de l'axe pour éviter les déformations
    pos = ax.get_position()
    ratio_ax = (pos.height * C.A3_PAYSAGE[1]) / (pos.width * C.A3_PAYSAGE[0])
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    w, h = (xmax - xmin) + 2 * pad, (ymax - ymin) + 2 * pad
    if h / w > ratio_ax:
        w = h / ratio_ax
    else:
        h = w * ratio_ax
    C.fond_territoire(ax, com, cadre=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    autres = com[com.code_insee != insee]
    autres.plot(ax=ax, color=C.HORS_TERRITOIRE, edgecolor="white", lw=1.2, zorder=1)
    zone.plot(ax=ax, color="white", edgecolor="none", zorder=1)
    zc = zones[zones.code_insee == insee]
    zc[zc.famille == "U"].plot(ax=ax, color="#f4f1ea", edgecolor="none", zorder=2)
    zc[zc.famille == "AU"].plot(ax=ax, facecolor="none", edgecolor=C.ZONES["AU"][1], hatch="////",
                                lw=0.8, zorder=3)
    parc_u.boundary.plot(ax=ax, color="#cfccc4", lw=0.25, zorder=4)
    excl_c = gpd.clip(excl, parc_u.union_all())  # contraintes affichées dans les zones étudiées
    if not excl_c.empty:
        excl_c.plot(ax=ax, facecolor="none", edgecolor="#4f8f4a", hatch="....", lw=0, zorder=5)
    bati[bati.code_insee == insee].plot(ax=ax, color="#6b6a66", edgecolor="none", zorder=6)
    for t, coul in TYPES.items():
        sel = g[g.type_gisement == t]
        if not sel.empty:
            sel.plot(ax=ax, color=coul, edgecolor="white", lw=0.4, zorder=8)
    vig = g[g.vigilance != ""]
    if not vig.empty:
        vig.boundary.plot(ax=ax, color=C.ENCRE, lw=0.9, linestyle=(0, (2, 1.5)), zorder=9)
    zone.boundary.plot(ax=ax, color=C.ENCRE, lw=1.4, zorder=10)
    C.echelle_nord(ax)

    P = C.Panneau(axp)
    P.titre("Potentiel identifié")
    P.chiffre(f"{len(g)} terrains", f"soit {C.fr(g.surface_libre_m2.sum() / 1e4, 1, 'ha')} mobilisables "
              "dans l'enveloppe urbaine")
    P.chiffre(f"≈ {C.fr(g.logements_mobilisables.sum(), 0)} logements",
              f"à 10 ans après rétention foncière ({C.fr(g.logements_bruts.sum(), 0)} en potentiel brut)")
    for t in TYPES:
        s = g[g.type_gisement == t]
        if len(s):
            P.texte(f"• {t} : {len(s)} terrains, {C.fr(s.surface_libre_m2.sum() / 1e4, 1, 'ha')}",
                    taille=8.5, couleur=C.ENCRE)
    P.espace(0.012)
    P.titre("Légende")
    for t, coul in TYPES.items():
        P.case(coul, t)
    P.case("white", "Gisement à arbitrer (boisé ou en OAP)", bord=C.ENCRE)
    P.case("#6b6a66", "Bâti (BD TOPO)")
    P.case("#f4f1ea", "Zone urbaine (U) du PLUi", bord="#cfccc4")
    P.case("white", "Zone à urbaniser (AU)", hachure="////", bord=C.ZONES["AU"][1])
    P.case("white", "Prescription excluante (EBC, paysage, risque)", hachure="....", bord="#4f8f4a")
    P.espace(0.012)
    P.titre("Hypothèses")
    P.texte(f"Densité {config.DENSITE_LOG_HA} logements/ha ; mobilisation à 10 ans : dents creuses "
            f"{C.pct(config.TAUX_MOBILISATION['Dent creuse'] * 100)}, divisions "
            f"{C.pct(config.TAUX_MOBILISATION['Division parcellaire'] * 100)}, grands tènements "
            f"{C.pct(config.TAUX_MOBILISATION['Grand tènement'] * 100)}. Recul de {config.TAMPON_BATI_M} m "
            f"autour du bâti, lot minimal {config.SEUIL_DENT_CREUSE_M2} m² pouvant contenir un carré "
            f"de {config.LARGEUR_MIN_LOT_M} m et ouvert sur la voie publique sur au moins "
            f"{config.FACADE_MIN_M} m ({synth_c['nb_enclaves']} terrains enclavés écartés). "
            "Résultat à valider sur le terrain (pente, réseaux, servitudes, volonté des "
            "propriétaires).", largeur=52)
    C.cartouche(fig, "DGFiP/IGN, Parcellaire Express ; IGN, BD TOPO, OCS GE 2022 ; Géoportail de "
                     "l'Urbanisme, PLUi approuvé le 04/05/2026 (zonage et prescriptions)")
    return fig


def main():
    log("Étape 4 - Gisements de densification")
    com = lire("communes")
    zone_etude = com[com.code_insee.isin(list(config.COMMUNES_DENSIFICATION))]
    zones = lire("plui_zonage_qualifie")
    parc = lire("cadastre_parcelles")
    bati = lire("bdtopo_batiments")
    bati["geometry"] = shapely.force_2d(bati.geometry.values)
    bati = bati[(bati.construction_legere != True) & (bati.area >= config.SURFACE_BATI_MIN_M2)]  # noqa: E712
    presc = prescriptions(zone_etude)
    excl = presc[presc.apply(est_excluante, axis=1)]
    oap = presc[presc.typepsc == "18"]
    ocs = lire("ocsge_2022_classee", bbox=tuple(zone_etude.total_bounds))

    gis, parcs = [], []
    for insee, nom in config.COMMUNES_DENSIFICATION.items():
        geom_c = com.loc[com.code_insee == insee].geometry.iloc[0]
        g, p = analyser_commune(insee, nom, geom_c, parc, zones, bati, excl, oap, ocs)
        gis.append(g)
        parcs.append(p)
    g = gpd.GeoDataFrame(pd.concat(gis, ignore_index=True), crs=config.CRS)
    p = gpd.GeoDataFrame(pd.concat(parcs, ignore_index=True), crs=config.CRS)
    g = g[["code_insee", "commune", "idu", "zone_plui", "type_gisement", "surface_m2", "surface_libre_m2",
           "emprise_bati_m2", "coef_emprise", "facade_voie_m", "part_boisee", "dans_oap", "vigilance",
           "logements_bruts", "taux_mobilisation", "logements_mobilisables", "geometry"]]
    ecrire(g, "gisements_densification")
    ecrire(p, "parcelles_zone_u_etude")
    ecrire(excl, "contraintes_prescriptions")

    synth = {}
    for insee, nom in config.COMMUNES_DENSIFICATION.items():
        gc = g[g.code_insee == insee]
        synth[nom] = {
            "nb_gisements": int(len(gc)),
            "nb_enclaves": int(p[(p.code_insee == insee) & p.enclave].shape[0]),
            "surface_ha": gc.surface_libre_m2.sum() / 1e4,
            "logements_bruts": int(gc.logements_bruts.sum()),
            "logements_mobilisables": float(gc.logements_mobilisables.sum()),
            **{f"nb_{t}": int((gc.type_gisement == t).sum()) for t in TYPES},
            **{f"ha_{t}": gc.loc[gc.type_gisement == t, "surface_libre_m2"].sum() / 1e4 for t in TYPES},
        }
        fig = carte_commune(insee, nom, gc, p[p.code_insee == insee], com, zones, bati, excl, synth[nom])
        num = 7 + list(config.COMMUNES_DENSIFICATION).index(insee)
        C.enregistrer(fig, f"C{num:02d}_Gisements_densification_{nom.replace(' ', '-')}")
    (config.INTERIM / "synthese_etape4.json").write_text(json.dumps(synth, indent=1, ensure_ascii=False), encoding="utf-8")
    for nom, s in synth.items():
        log(f"  {nom}: {s['nb_gisements']} gisements, {s['surface_ha']:.1f} ha, "
            f"{s['logements_bruts']} logts bruts, {s['logements_mobilisables']:.0f} mobilisables")
    log("Étape 4 terminée")


if __name__ == "__main__":
    main()
