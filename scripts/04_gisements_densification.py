"""Étape 4 - Repérage des gisements fonciers de densification (zones U à vocation habitat).

Méthode (inspirée des études de densification prévues à l'art. L.151-5 du
Code de l'urbanisme, sans visite de terrain) :
  1. Parcelles cadastrales (Etalab) situées majoritairement en zone U à dominante habitat.
  2. Emprise du bâti BD TOPO (hors constructions légères et annexes < 20 m²).
  3. Espace libre = parcelle - tampon de 5 m autour du bâti - prescriptions excluantes
     du PLUi (EBC, patrimoine paysager, risques de cavités et aléas forts, emplacements
     réservés d'infrastructures).
  4. « Ouverture » morphologique de 7,5 m : on ne garde que les espaces où un carré
     de 15 m de côté peut s'inscrire (forme de lot constructible).
  5. Accès : contact d'au moins 4 m avec la voie publique ou une voie de lotissement.
  6. Typologie : dent creuse (parcelle non bâtie), grand tènement (> 5 000 m² non bâtis),
     division parcellaire (parcelle bâtie > 1 200 m², emprise < 15 %).
  7. Potentiel de logements = surface x densité, puis pondération par un taux de
     mobilisation à 10 ans (observé pour les divisions, étape 4 bis).

Le repérage couvre les 71 communes ; les planches détaillées C07 et C08 portent sur les
deux communes test, et un atlas dédié (08_Atlas_gisements) présente chaque commune.
"""
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, Ellipse, Rectangle

import cartes as C
import config
from outils import cadastre_etalab, couches, ecrire, fond_eau, lire, log, wfs

TYPES = {
    "Dent creuse": "#b8262b",
    "Grand tènement": "#6e1414",
    "Division parcellaire": "#f0a04b",
}
PREFIXES_HABITAT = ("UA", "UB", "UC", "UD", "UR")
DOSSIER_ATLAS = config.LIVRABLES / "08_Atlas_gisements"
TUILE_M = 400  # découpage de la voirie en tuiles : intersections plus rapides


# --- Données ----------------------------------------------------------------------------
def prescriptions(com):
    if "plui_prescriptions_metropole" in couches():
        return lire("plui_prescriptions_metropole")
    b = com.total_bounds
    log("  téléchargement des prescriptions surfaciques du PLUi (Métropole)")
    docs = lire("plui_zonage").idurba.iloc[0]
    p = wfs("wfs_du:prescription_surf",
            cql=f"idurba='{docs}' AND BBOX(the_geom,{b[0]},{b[1]},{b[2]},{b[3]},'EPSG:2154')",
            sort="gid")
    p = p[["typepsc", "stypepsc", "libelle", "geometry"]]
    p["geometry"] = p.geometry.make_valid()
    ecrire(p, "plui_prescriptions_metropole")
    return p


def batiments(com):
    """Bâti BD TOPO de toutes les communes (WFS par commune, mis en cache)."""
    if "bdtopo_batiments_metropole" in couches():
        return lire("bdtopo_batiments_metropole")
    log("  téléchargement du bâti BD TOPO (71 communes)")
    morceaux = []
    for _, c in com.iterrows():
        zone = com[com.code_insee == c.code_insee]
        b = wfs("BDTOPO_V3:batiment", bbox=zone.total_bounds, sort="cleabs")
        if b.empty:
            continue
        b = gpd.clip(b, zone)
        b["code_insee"] = c.code_insee
        morceaux.append(b[["cleabs", "construction_legere", "code_insee", "geometry"]])
    bati = gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True), crs=config.CRS)
    bati["geometry"] = shapely.force_2d(bati.geometry.values)
    ecrire(bati, "bdtopo_batiments_metropole")
    return bati


def est_excluante(row):
    regle = config.PRESCRIPTIONS_EXCLUANTES.get(row.typepsc, False)
    if regle is False:
        return False
    if regle is None:
        return True
    lib = str(row.libelle).lower()
    return any(m.lower() in lib for m in regle)


def tuiles(geom, taille=TUILE_M):
    """Découpe une grande géométrie (voirie) en tuiles pour profiter de l'index spatial."""
    xmin, ymin, xmax, ymax = geom.bounds
    cases = [shapely.box(x, y, x + taille, y + taille)
             for x in np.arange(xmin, xmax, taille) for y in np.arange(ymin, ymax, taille)]
    t = gpd.GeoDataFrame(geometry=shapely.intersection(np.array(cases), geom), crs=config.CRS)
    return t[~t.geometry.is_empty]


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


def analyser_commune(insee, nom, geom_commune, zones, bati, excl, oap, ocs):
    parc = cadastre_etalab(insee, config.CADASTRE_GISEMENTS).rename(columns={"id": "idu"})
    p = parc[["idu", "contenance", "geometry"]].copy()
    p["surface_m2"] = p.area
    voirie = domaine_public(geom_commune, p, ocs[(ocs.code_insee == insee) & (ocs.code_us == "US4.1.1")])
    u = zones[(zones.code_insee == insee) & (zones.famille == "U")
              & zones.libelle.str.startswith(PREFIXES_HABITAT) & ~zones.libelle.str.startswith("URX")]
    if u.empty:
        return None, None, 0
    x = gpd.overlay(p[["idu", "geometry"]], u[["libelle", "geometry"]], how="intersection", keep_geom_type=True)
    x["a"] = x.area
    part_u = x.groupby("idu").a.sum() / p.set_index("idu").surface_m2
    zone_maj = x.sort_values("a").groupby("idu").libelle.last()
    p = p[p.idu.map(part_u).fillna(0) >= 0.5].copy()
    p["zone_plui"] = p.idu.map(zone_maj)
    if p.empty:
        return None, None, 0

    b = bati[bati.code_insee == insee]
    xb = gpd.overlay(p[["idu", "geometry"]], b[["geometry"]], how="intersection", keep_geom_type=True)
    p["emprise_bati_m2"] = p.idu.map(xb.area.groupby(xb.idu).sum()).fillna(0)
    p["coef_emprise"] = p.emprise_bati_m2 / p.surface_m2

    # espace libre : on ne retire à chaque parcelle que les tampons et contraintes voisins (index spatial)
    tampons = gpd.GeoDataFrame(geometry=b.geometry.buffer(config.TAMPON_BATI_M, resolution=4), crs=config.CRS)
    libre = gpd.overlay(p[["idu", "geometry"]], tampons, how="difference") if len(tampons) else p[["idu", "geometry"]]
    xmin, ymin, xmax, ymax = geom_commune.bounds
    excl_c = excl.cx[xmin:xmax, ymin:ymax]
    if len(excl_c) and len(libre):
        libre = gpd.overlay(libre, excl_c[["geometry"]], how="difference")
    d = config.LARGEUR_MIN_LOT_M / 2
    g0 = libre.geometry.values
    ouv = shapely.buffer(shapely.buffer(g0, -d, join_style="mitre"), d, join_style="mitre")
    libre["geometry"] = shapely.make_valid(shapely.intersection(ouv, g0))
    libre = libre[~libre.geometry.is_empty & (libre.area > 0)]
    p["surface_libre_m2"] = p.idu.map(libre.set_index("idu").area).fillna(0)
    # accès : contact d'au moins 4 m entre l'espace libre et la voie
    if len(libre):
        bord = gpd.GeoDataFrame({"idu": libre.idu.values}, geometry=libre.geometry.buffer(2).values, crs=config.CRS)
        xc = gpd.overlay(bord, tuiles(voirie), how="intersection", keep_geom_type=True)
        p["facade_voie_m"] = p.idu.map(xc.area.groupby(xc.idu).sum() / 2).fillna(0).round(1)
    else:
        p["facade_voie_m"] = 0.0
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
    sel = p[p.type_gisement != ""]
    geom_libre = libre.dissolve("idu").geometry
    g = gpd.GeoDataFrame(sel.drop(columns="geometry"), geometry=sel.idu.map(geom_libre).values, crs=config.CRS)
    g["code_insee"], g["commune"] = insee, nom

    # emprises de transport et de réseaux (voies ferrées, routes, logistique) : exclues
    o = ocs[ocs.code_insee == insee]
    if len(g):
        xt = gpd.overlay(g[["idu", "geometry"]], o[o.code_us.str.startswith("US4")][["geometry"]],
                         how="intersection", keep_geom_type=True)
        part_transport = g.idu.map(xt.area.groupby(xt.idu).sum()).fillna(0) / g.area
        g = g[part_transport.values <= 0.5].copy()
    # boisement (OCS GE) et OAP : signalés, à arbitrer
    if len(g):
        xo = gpd.overlay(g[["idu", "geometry"]], o[o.code_cs.str.startswith("CS2.1")][["geometry"]],
                         how="intersection", keep_geom_type=True)
        g["part_boisee"] = (g.idu.map(xo.area.groupby(xo.idu).sum()).fillna(0) / g.area).round(3)
        oap_c = oap.cx[xmin:xmax, ymin:ymax]
        g["dans_oap"] = g.geometry.intersects(shapely.union_all(oap_c.geometry.values)) if len(oap_c) else False
    else:
        g["part_boisee"], g["dans_oap"] = 0.0, False
    g["vigilance"] = np.where(g.part_boisee > 0.5, "Terrain boisé à plus de 50 % : à arbitrer",
                              np.where(g.dans_oap, "Dans le périmètre d'une OAP", ""))
    g["logements_bruts"] = np.maximum(1, np.floor(g.surface_libre_m2 / 1e4 * config.DENSITE_LOG_HA)).astype(int)
    g["taux_mobilisation"] = g.type_gisement.map(config.TAUX_MOBILISATION)
    g["logements_mobilisables"] = g.logements_bruts * g.taux_mobilisation
    p["code_insee"], p["commune"] = insee, nom
    return g, p, int(p.enclave.sum())


# --- Planche détaillée (communes test) ----------------------------------------------------
def carte_commune(insee, nom, g, parc_u, com, zones, bati, excl, synth_c):
    fig, ax, axp = C.planche(f"Gisements fonciers de densification : {nom}",
                             "Repérage automatisé dans les zones urbaines à dominante habitat du PLUi")
    zone = com[com.code_insee == insee]
    xmin, ymin, xmax, ymax = zone.total_bounds
    pad = 250
    pos = ax.get_position()
    ratio_ax = (pos.height * C.A3_PAYSAGE[1]) / (pos.width * C.A3_PAYSAGE[0])
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    w, h = (xmax - xmin) + 2 * pad, (ymax - ymin) + 2 * pad
    if h / w > ratio_ax:
        w = h / ratio_ax
    else:
        h = w * ratio_ax
    C.fond_territoire(ax, com, cadre=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    com[com.code_insee != insee].plot(ax=ax, color=C.HORS_TERRITOIRE, edgecolor="white", lw=1.2, zorder=1)
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
    P.texte(texte_hypotheses(synth_c["nb_enclaves"]), largeur=52)
    C.cartouche(fig, f"DGFiP, cadastre Etalab ({config.CADASTRE_GISEMENTS}) ; IGN, BD TOPO, OCS GE 2022 ; "
                     "Géoportail de l'Urbanisme, PLUi approuvé le 04/05/2026 (zonage et prescriptions)")
    return fig


def texte_hypotheses(nb_enclaves=None):
    t = (f"Densité {config.DENSITE_LOG_HA} logements/ha ; mobilisation à 10 ans : dents creuses "
         f"{C.pct(config.TAUX_MOBILISATION['Dent creuse'] * 100)}, divisions "
         f"{C.pct(config.TAUX_MOBILISATION['Division parcellaire'] * 100)} (taux observé 2018-2026), grands "
         f"tènements {C.pct(config.TAUX_MOBILISATION['Grand tènement'] * 100)}. Recul de {config.TAMPON_BATI_M} m "
         f"autour du bâti, lot minimal {config.SEUIL_DENT_CREUSE_M2} m² pouvant contenir un carré de "
         f"{config.LARGEUR_MIN_LOT_M} m et ouvert sur la voie sur au moins {config.FACADE_MIN_M} m")
    t += f" ({nb_enclaves} terrains enclavés écartés). " if nb_enclaves is not None else ". "
    return t + "Résultat à valider sur le terrain (pente, réseaux, servitudes, volonté des propriétaires)."


# --- Planche de synthèse et atlas (71 communes) ------------------------------------------
def planche_synthese(ind, com, perim, eau, synth):
    fig, ax, axp = C.planche("Gisements de densification dans les 71 communes",
                             "Potentiel de logements mobilisables à 10 ans dans les zones U à dominante habitat")
    C.fond_territoire(ax, com)
    com.plot(ax=ax, color="#f6f5f1", edgecolor="none", zorder=1)
    C.surcouches(ax, com, eau, perim)
    g = com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee")
    dense = g[g.tissu_dense]
    if not dense.empty:
        dense.plot(ax=ax, facecolor="none", edgecolor="#898781", hatch="xx", lw=0, zorder=2)
    vmax, rmax = max(g.gis_log_mob.max(), 1), 2000
    for _, r in g[g.gis_log_mob > 0].sort_values("gis_log_mob", ascending=False).iterrows():
        pt = r.geometry.representative_point()
        coul = "#bdbbb4" if r.tissu_dense else TYPES["Division parcellaire"]  # centres denses : à relativiser
        ax.add_patch(Circle((pt.x, pt.y), rmax * np.sqrt(r.gis_log_mob / vmax), facecolor=coul,
                            alpha=0.9, edgecolor="white", lw=1, zorder=10))
    for _, r in g.nlargest(8, "gis_log_mob").iterrows():
        pt = r.geometry.representative_point()
        ax.annotate(f"{r.nom}\n≈ {C.fr(r.gis_log_mob, 0)}", (pt.x, pt.y), ha="center", va="center", fontsize=7.5,
                    color=C.ENCRE, fontweight="semibold", zorder=20,
                    path_effects=[C.pe.withStroke(linewidth=2.6, foreground="white")])
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Chiffres clés")
    P.chiffre(C.fr(synth["nb_gisements"], 0), f"terrains repérés, soit {C.fr(synth['surface_ha'], 0, 'ha')} "
              "dans l'enveloppe urbaine")
    P.chiffre(f"≈ {C.fr(synth['logements_mobilisables'], 0)}", "logements mobilisables à 10 ans "
              f"({C.fr(synth['logements_bruts'], 0)} en potentiel brut)")
    P.espace(0.01)
    P.titre("Légende")
    P.texte("Logements mobilisables à 10 ans", taille=8.5, couleur=C.ENCRE)
    x0, x1 = ax.get_xlim()
    pc, pp = ax.get_position(), axp.get_position()
    ech = (pc.width / (x1 - x0)) / pp.width
    ratio = (pp.height * C.A3_PAYSAGE[1]) / (pp.width * C.A3_PAYSAGE[0])
    pas = [v for v in (1000, 500, 200, 100, 50) if v <= vmax * 1.05][:3] or [int(vmax)]
    rleg = rmax * np.sqrt(pas[0] / vmax) * ech
    cx, base = 0.02 + rleg, P.y - 2 * rleg / ratio - 0.005
    for v in pas:
        r = rmax * np.sqrt(v / vmax) * ech
        axp.add_patch(Ellipse((cx, base + r / ratio), 2 * r, 2 * r / ratio, facecolor="none",
                              edgecolor=C.ENCRE_2, lw=0.8))
        axp.plot([cx, cx + rleg + 0.04], [base + 2 * r / ratio] * 2, color=C.ENCRE_3, lw=0.5)
        axp.text(cx + rleg + 0.05, base + 2 * r / ratio, C.fr(v, 0), va="center", fontsize=8, color=C.ENCRE)
    P.y = base - 0.03
    P.case(TYPES["Division parcellaire"], "Commune à dominante pavillonnaire")
    P.case("#bdbbb4", f"Centre urbain dense (> {config.SEUIL_TISSU_DENSE_HAB_HA} hab./ha) : méthode moins "
                      "adaptée, à relativiser", hachure="xx", bord="#898781")
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.01)
    P.titre("Hypothèses")
    P.texte(texte_hypotheses(), largeur=52)
    C.cartouche(fig, f"DGFiP, cadastre Etalab ({config.CADASTRE_GISEMENTS}) ; IGN, BD TOPO, OCS GE 2022, "
                     "ADMIN EXPRESS ; Géoportail de l'Urbanisme (PLUi 04/05/2026)")
    return fig


def atlas_couverture(pdf, synth, n):
    fig = plt.figure(figsize=C.A4_PAYSAGE)
    fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.07, 0.70, "Atlas des gisements de densification", color="white", fontsize=32, fontweight="bold")
    fig.text(0.07, 0.62, "Terrains mobilisables dans les zones urbaines à dominante habitat", color="#dce8f6",
             fontsize=17)
    fig.text(0.07, 0.56, f"{config.EPCI_NOM} · {n} communes", color="white", fontsize=13)
    fig.text(0.07, 0.52, "Étude indépendante réalisée à partir de données ouvertes - document non officiel",
             color="#dce8f6", fontsize=10)
    fig.text(0.07, 0.40, f"{C.fr(synth['nb_gisements'], 0)} terrains · {C.fr(synth['surface_ha'], 0, 'ha')} · "
             f"≈ {C.fr(synth['logements_mobilisables'], 0)} logements mobilisables à 10 ans", color="white", fontsize=12)
    fig.text(0.07, 0.30, "Repérage automatisé sans visite de terrain : chaque terrain est à vérifier (pente, accès,\n"
             "réseaux, servitudes, volonté des propriétaires). Dans les centres denses, la méthode, pensée pour le\n"
             "tissu pavillonnaire, est moins adaptée.", color="#dce8f6", fontsize=10, va="top", linespacing=1.6)
    fig.text(0.07, 0.07, f"Réalisation : {config.AUTEUR}", color="#dce8f6", fontsize=10)
    fig.text(0.07, 0.04, f"Sources : DGFiP, cadastre Etalab ({config.CADASTRE_GISEMENTS}) ; IGN, BD TOPO, OCS GE 2022 ; "
             "Géoportail de l'Urbanisme", color="#dce8f6", fontsize=8.5)
    pdf.savefig(fig)
    plt.close(fig)


def atlas_synthese(pdf, ind):
    fig = plt.figure(figsize=C.A4_PAYSAGE, facecolor="white")
    fig.add_artist(Rectangle((0, 0.915), 1, 0.085, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.03, 0.958, "Tableau de synthèse par commune", color="white", fontsize=17, fontweight="bold",
             va="center")
    t = ind[ind.gis_nb > 0].sort_values("gis_log_mob", ascending=False).head(40)
    cols = [("Commune", "nom", 0.03), ("Terrains", "gis_nb", 0.40), ("Surface (ha)", "gis_ha", 0.52),
            ("Dents creuses", "gis_nb_dc", 0.65), ("Divisions", "gis_nb_div", 0.78), ("Logts 10 ans", "gis_log_mob", 0.89)]
    for j, demi in enumerate((t.iloc[:20], t.iloc[20:])):
        if demi.empty:
            continue
        dx, ech = (0 if j == 0 else 0.48), 0.48 / 0.97
        y = 0.87
        for lib, _, x in cols:
            fig.text(dx + x * ech + 0.01, y, lib, fontsize=7, fontweight="bold", color=C.ACCENT)
        for _, r in demi.iterrows():
            y -= 0.038
            for lib, col, x in cols:
                v = r[col]
                txt = (r.nom + (" *" if r.tissu_dense else "")) if col == "nom" else C.fr(v, 1 if col == "gis_ha" else 0)
                fig.text(dx + x * ech + 0.01, y, txt, fontsize=7.5, color=C.ENCRE)
            fig.add_artist(plt.Line2D([dx + 0.01, dx + 0.47], [y - 0.012] * 2, transform=fig.transFigure,
                                      color=C.GRILLE, lw=0.4))
    fig.text(0.03, 0.04, "Communes classées par logements mobilisables à 10 ans (40 premières). * centre urbain dense : "
             "la méthode, pensée pour le tissu pavillonnaire, y est moins adaptée.", fontsize=7, color=C.ENCRE_3)
    pdf.savefig(fig)
    plt.close(fig)


def atlas_page(pdf, r, g_c, com, zones, eau, num, total):
    fig = plt.figure(figsize=C.A4_PAYSAGE, facecolor="white")
    fig.add_artist(Rectangle((0, 0.915), 1, 0.085, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.03, 0.958, r.nom, color="white", fontsize=17, fontweight="bold", va="center")
    fig.text(0.97, 0.958, f"Gisements de densification · INSEE {r.code_insee}", color="#dce8f6", fontsize=9.5,
             ha="right", va="center")
    ax = fig.add_axes([0.02, 0.07, 0.6, 0.83])
    ax.set_axis_off()
    geom = com[com.code_insee == r.code_insee]
    xmin, ymin, xmax, ymax = geom.total_bounds
    pos = ax.get_position()
    ratio = (pos.height * C.A4_PAYSAGE[1]) / (pos.width * C.A4_PAYSAGE[0])
    cx, cy, w, h = (xmin + xmax) / 2, (ymin + ymax) / 2, (xmax - xmin) * 1.1, (ymax - ymin) * 1.1
    w, h = (h / ratio, h) if h / w > ratio else (w, w * ratio)
    ax.set_xlim(cx - w / 2, cx + w / 2)
    ax.set_ylim(cy - h / 2, cy + h / 2)
    ax.set_aspect("equal")
    ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, color=C.HORS_TERRITOIRE, zorder=0))
    geom.plot(ax=ax, color="#f6f5f1", edgecolor="none", zorder=1)
    zc = zones[zones.code_insee == r.code_insee]
    zc[zc.famille == "U"].plot(ax=ax, color="#ece6dc", edgecolor="none", zorder=2, rasterized=True)
    zc[zc.famille == "AU"].plot(ax=ax, facecolor="none", edgecolor=C.ZONES["AU"][1], hatch="////", lw=0.6, zorder=3)
    if eau is not None:
        gpd.clip(eau, geom.buffer(3000)).plot(ax=ax, color=C.EAU, edgecolor="none", zorder=3)
    for t, coul in TYPES.items():
        sel = g_c[g_c.type_gisement == t]
        if not sel.empty:  # contour de même teinte : petits terrains lisibles à l'échelle communale
            sel.plot(ax=ax, color=coul, edgecolor=coul, lw=0.5, zorder=6)
    com.boundary.plot(ax=ax, color="white", lw=1.2, zorder=4)
    geom.boundary.plot(ax=ax, color=C.ENCRE, lw=1.3, zorder=8)
    C.echelle_nord(ax)

    def ligne(y, lib, val, gras=False):
        fig.text(0.65, y, lib, fontsize=8.5, color=C.ENCRE_2, va="center")
        fig.text(0.97, y, val, fontsize=9 if gras else 8.5, color=C.ENCRE, ha="right", va="center",
                 fontweight="bold" if gras else "normal")
        fig.add_artist(plt.Line2D([0.65, 0.97], [y - 0.014] * 2, transform=fig.transFigure, color=C.GRILLE, lw=0.5))
    fig.text(0.65, 0.885, "POTENTIEL DANS LES ZONES U À DOMINANTE HABITAT", fontsize=8.5, fontweight="bold",
             color=C.ACCENT)
    y = 0.85
    for lib, val, gras in (("Terrains repérés", C.fr(r.gis_nb, 0), True),
                           ("Surface mobilisable", C.fr(r.gis_ha, 1, "ha"), True),
                           ("Logements mobilisables à 10 ans", f"≈ {C.fr(r.gis_log_mob, 0)}", True),
                           ("Potentiel brut (logements)", C.fr(r.gis_log_bruts, 0), False),
                           ("Dents creuses / grands tènements", f"{C.fr(r.gis_nb_dc, 0)} / {C.fr(r.gis_nb_gt, 0)}", False),
                           ("Divisions parcellaires possibles", C.fr(r.gis_nb_div, 0), False)):
        ligne(y, lib, val, gras)
        y -= 0.034
    y -= 0.02
    for t, coul in TYPES.items():
        fig.add_artist(Rectangle((0.65, y), 0.014, 0.016, transform=fig.transFigure, color=coul))
        fig.text(0.67, y + 0.008, t, fontsize=7.5, color=C.ENCRE, va="center")
        y -= 0.026
    fig.add_artist(Rectangle((0.65, y), 0.014, 0.016, transform=fig.transFigure, color="#ece6dc"))
    fig.text(0.67, y + 0.008, "Zone urbaine (U) du PLUi", fontsize=7.5, color=C.ENCRE, va="center")
    y -= 0.04
    if r.tissu_dense:
        fig.add_artist(Rectangle((0.645, y - 0.075), 0.33, 0.085, transform=fig.transFigure, color="#fdf1e6"))
        fig.text(0.655, y, "Centre urbain dense : la méthode, pensée pour le tissu pavillonnaire, repère\n"
                 "surtout des cours et des cœurs d'îlot. Résultat à interpréter avec prudence.", fontsize=7.5,
                 color=C.ENCRE, va="top", linespacing=1.5)
        y -= 0.1
    fig.text(0.65, y, "Repérage automatisé sans visite de terrain : pente, accès, réseaux,\nservitudes et "
             "volonté des propriétaires restent à vérifier.", fontsize=7, color=C.ENCRE_3, va="top", linespacing=1.5)
    fig.text(0.03, 0.025, f"Sources : DGFiP, cadastre Etalab ({config.CADASTRE_GISEMENTS}) ; IGN BD TOPO, OCS GE 2022, "
             "ADMIN EXPRESS ; Géoportail de l'Urbanisme (PLUi 04/05/2026).", fontsize=6.5, color=C.ENCRE_3)
    fig.text(0.97, 0.025, f"{config.AUTEUR} · page {num}/{total}", fontsize=6.5, color=C.ENCRE_3, ha="right")
    pdf.savefig(fig, dpi=200)
    plt.close(fig)


def atlas(g, ind, com, zones, eau, synth):
    DOSSIER_ATLAS.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_ATLAS / "Atlas_gisements_densification_Metropole_Rouen.pdf"
    sel = com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee")
    sel = sel[sel.gis_nb > 0].sort_values("nom")
    total = len(sel) + 2
    with PdfPages(chemin) as pdf:
        atlas_couverture(pdf, synth, len(sel))
        atlas_synthese(pdf, ind.merge(com[["code_insee", "nom"]], on="code_insee"))
        for i, (_, r) in enumerate(sel.iterrows(), start=3):
            atlas_page(pdf, r, g[g.code_insee == r.code_insee], com, zones, eau, i, total)
        meta = pdf.infodict()
        meta["Title"] = f"Atlas des gisements de densification - {config.EPCI_NOM}"
        meta["Author"] = config.AUTEUR
    log(f"  atlas des gisements : {chemin.name} ({total} pages)")


def main():
    log("Étape 4 - Gisements de densification")
    com = lire("communes")
    zones = lire("plui_zonage_qualifie")
    bati = batiments(com)
    bati = bati[(bati.construction_legere != True) & (bati.area >= config.SURFACE_BATI_MIN_M2)]  # noqa: E712
    presc = prescriptions(com)
    excl = presc[presc.apply(est_excluante, axis=1)]
    oap = presc[presc.typepsc == "18"]
    ocs = lire("ocsge_2022_classee")
    tests = list(config.COMMUNES_DENSIFICATION)
    a_traiter = com if config.DENSIFICATION_METROPOLE else com[com.code_insee.isin(tests)]

    gis, parcs, enclaves = [], [], {}
    for _, c in a_traiter.iterrows():
        g, p, n_encl = analyser_commune(c.code_insee, c.nom, c.geometry, zones, bati, excl, oap, ocs)
        enclaves[c.code_insee] = n_encl
        if g is not None and len(g):
            gis.append(g)
        if p is not None and c.code_insee in tests:
            parcs.append(p)
        log(f"  {c.nom} : {0 if g is None else len(g)} gisements")
    g = gpd.GeoDataFrame(pd.concat(gis, ignore_index=True), crs=config.CRS)
    p = gpd.GeoDataFrame(pd.concat(parcs, ignore_index=True), crs=config.CRS)
    g = g[["code_insee", "commune", "idu", "zone_plui", "type_gisement", "surface_m2", "surface_libre_m2",
           "emprise_bati_m2", "coef_emprise", "facade_voie_m", "part_boisee", "dans_oap", "vigilance",
           "logements_bruts", "taux_mobilisation", "logements_mobilisables", "geometry"]]
    ecrire(g, "gisements_densification")
    ecrire(p, "parcelles_zone_u_etude")
    ecrire(excl, "contraintes_prescriptions")

    # indicateurs communaux
    conso = lire("ind_conso_enaf")
    densite = (conso.set_index("code_insee").pop_2022 / conso.set_index("code_insee").surface_com_ha)
    gg = g.groupby("code_insee")
    ind = pd.DataFrame({"code_insee": com.code_insee})
    ind["gis_nb"] = ind.code_insee.map(gg.size()).fillna(0).astype(int)
    ind["gis_ha"] = ind.code_insee.map(gg.surface_libre_m2.sum() / 1e4).fillna(0).round(2)
    ind["gis_log_bruts"] = ind.code_insee.map(gg.logements_bruts.sum()).fillna(0).astype(int)
    ind["gis_log_mob"] = ind.code_insee.map(gg.logements_mobilisables.sum()).fillna(0).round(1)
    for t, cle in (("Dent creuse", "dc"), ("Division parcellaire", "div"), ("Grand tènement", "gt")):
        ind[f"gis_nb_{cle}"] = ind.code_insee.map(g[g.type_gisement == t].groupby("code_insee").size()).fillna(0).astype(int)
    ind["densite_hab_ha"] = ind.code_insee.map(densite).round(1)
    ind["tissu_dense"] = ind.densite_hab_ha >= config.SEUIL_TISSU_DENSE_HAB_HA
    ecrire(com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee"), "ind_gisements")

    # synthèses : communes test (détail) et Métropole
    synth = {}
    for insee in tests:
        nom = config.COMMUNES_DENSIFICATION[insee]
        gc = g[g.code_insee == insee]
        synth[nom] = {
            "nb_gisements": int(len(gc)), "nb_enclaves": enclaves.get(insee, 0),
            "surface_ha": gc.surface_libre_m2.sum() / 1e4,
            "logements_bruts": int(gc.logements_bruts.sum()),
            "logements_mobilisables": float(gc.logements_mobilisables.sum()),
            **{f"nb_{t}": int((gc.type_gisement == t).sum()) for t in TYPES},
            **{f"ha_{t}": gc.loc[gc.type_gisement == t, "surface_libre_m2"].sum() / 1e4 for t in TYPES},
        }
        fig = carte_commune(insee, nom, gc, p[p.code_insee == insee], com, zones, bati, excl, synth[nom])
        C.enregistrer(fig, f"C{7 + tests.index(insee):02d}_Gisements_densification_{nom.replace(' ', '-')}")
    (config.INTERIM / "synthese_etape4.json").write_text(json.dumps(synth, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
    met = {
        "nb_communes": int((ind.gis_nb > 0).sum()), "nb_gisements": int(len(g)),
        "surface_ha": float(g.surface_libre_m2.sum() / 1e4), "logements_bruts": int(g.logements_bruts.sum()),
        "logements_mobilisables": float(g.logements_mobilisables.sum()),
        "par_type": {t: {"nb": int((g.type_gisement == t).sum()),
                         "ha": float(g.loc[g.type_gisement == t, "surface_libre_m2"].sum() / 1e4)} for t in TYPES},
        "communes_denses": com.set_index("code_insee").nom.reindex(ind[ind.tissu_dense].code_insee).tolist(),
        "logements_mobilisables_hors_denses": float(ind[~ind.tissu_dense].gis_log_mob.sum()),
    }
    (config.INTERIM / "synthese_etape4_metropole.json").write_text(json.dumps(met, indent=1, ensure_ascii=False),
                                                                    encoding="utf-8")
    eau, perim = fond_eau(), lire("perimetre")
    C.enregistrer(planche_synthese(ind, com, perim, eau, met), "C10_Gisements_densification_71_communes")
    atlas(g, ind, com, zones, eau, met)
    for nom, s in synth.items():
        log(f"  {nom}: {s['nb_gisements']} gisements, {s['surface_ha']:.1f} ha, "
            f"{s['logements_bruts']} logts bruts, {s['logements_mobilisables']:.0f} mobilisables")
    log(f"  Métropole : {met['nb_gisements']} gisements, {met['surface_ha']:.0f} ha, "
        f"{met['logements_mobilisables']:.0f} logements mobilisables")
    log("Étape 4 terminée")


if __name__ == "__main__":
    main()
