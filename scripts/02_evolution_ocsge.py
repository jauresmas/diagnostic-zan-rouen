"""Étape 2 - Occupation du sol et artificialisation 2019-2022 (OCS GE IGN).

- Classement de chaque polygone OCS GE (couverture x usage) en surface
  artificialisée ou non, selon la nomenclature annexée au décret
  n° 2023-1096 du 27 novembre 2023, appliquée sans les seuils de surface.
- Regroupement en 7 grandes classes d'occupation du sol (type MOS niveau 1).
- Stocks 2019 et 2022 par commune et flux 2019-2022 à partir du produit
  « différentiel » de l'IGN (changements détectés entre millésimes).
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import cartes as C
import config
from outils import ecrire, fond_eau, lire, log

# usages « urbains » : une couverture herbacée y est comptée comme artificialisée
US_URBAINS = {"US2", "US235", "US3", "US4.1.1", "US4.1.2", "US4.1.3", "US4.1.4", "US4.1.5",
              "US4.2", "US4.3", "US5", "US6.1", "US6.2"}

CLASSES = {  # code: (libellé, couleur) - teintes conventionnelles des MOS
    1: ("Bâti", "#b8262b"),
    2: ("Surfaces revêtues ou stabilisées", "#e88a73"),
    3: ("Espaces verts artificialisés", "#f2c4b8"),
    4: ("Espaces agricoles", "#efe08c"),
    5: ("Prairies, friches, milieux ouverts", "#b9d98c"),
    6: ("Forêts et boisements", "#4f8f4a"),
    7: ("Eau, sols nus, carrières", "#9fc3df"),
}


def est_artificialise(cs, us):
    cs, us = pd.Series(cs), pd.Series(us)
    impermeable_ou_stabilise = cs.str.startswith("CS1.1") & (us != "US1.3")
    herbace_urbain = cs.isin(["CS2.2.1", "CS2.2.2"]) & us.isin(US_URBAINS)
    return (impermeable_ou_stabilise | herbace_urbain).to_numpy()


def grande_classe(cs, us):
    cs, us = pd.Series(cs), pd.Series(us)
    art = est_artificialise(cs, us)
    c = np.select(
        [art & (cs == "CS1.1.1.1"),
         art & cs.str.startswith("CS1.1"),
         art,
         cs.str.startswith("CS1.2") | (us == "US1.3"),
         us == "US1.1",
         cs.str.startswith("CS2.1")],
        [1, 2, 3, 7, 4, 6],
        default=5,
    )
    return c


def stocks(annee):
    o = lire(f"ocsge_{annee}_occupation_sol")
    o["artif"] = est_artificialise(o.code_cs, o.code_us)
    o["classe"] = grande_classe(o.code_cs, o.code_us)
    o["surface_ha"] = o.area / 1e4
    return o


def flux():
    d = lire("ocsge_diff_2019_2022")
    d["artif_2019"] = est_artificialise(d.cs_2019, d.us_2019)
    d["artif_2022"] = est_artificialise(d.cs_2022, d.us_2022)
    d["classe_2019"] = grande_classe(d.cs_2019, d.us_2019)
    d["classe_2022"] = grande_classe(d.cs_2022, d.us_2022)
    d["surface_ha"] = d.area / 1e4
    d["type_flux"] = np.select(
        [~d.artif_2019 & d.artif_2022, d.artif_2019 & ~d.artif_2022],
        ["Artificialisation", "Désartificialisation"], default="Changement sans effet")
    return d


def famille_usage(us):
    if us == "US5":
        return "Habitat"
    if us in ("US2", "US3", "US235"):
        return "Activités et équipements"
    if us.startswith("US4"):
        return "Infrastructures et réseaux"
    if us == "US6.1":
        return "Chantiers (zones en transition)"
    return "Autres usages"


# --- Graphique : origine et destination de l'artificialisation ----------------------
def graphique_flux(d):
    art = d[d.type_flux == "Artificialisation"]
    orig = art.groupby("classe_2019").surface_ha.sum().reindex([4, 5, 6, 7], fill_value=0)
    dest = art.assign(f=art.us_2022.map(famille_usage)).groupby("f").surface_ha.sum()
    ordre_dest = ["Chantiers (zones en transition)", "Activités et équipements", "Habitat",
                  "Infrastructures et réseaux", "Autres usages"]
    dest = dest.reindex(ordre_dest, fill_value=0)
    dest = dest[dest > 0]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.0), sharex=True)
    fig.subplots_adjust(left=0.20, right=0.97, top=0.78, bottom=0.14, wspace=0.75)
    for ax, serie, titre, coul in (
        (a1, orig.rename(index=lambda k: CLASSES[k][0]).iloc[::-1], "D'où viennent les surfaces artificialisées ?\n(occupation en 2019)", C.ARTIF),
        (a2, dest.iloc[::-1], "Pour quel usage ?\n(usage en 2022)", C.ARTIF),
    ):
        ax.barh(serie.index, serie.values, color=coul, height=0.6, edgecolor="white")
        for y, v in enumerate(serie.values):
            ax.text(v + serie.max() * 0.02, y, C.fr(v, 1, "ha"), va="center", fontsize=8.5, color=C.ENCRE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(C.AXE)
        ax.xaxis.grid(True, color=C.GRILLE, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.set_title(titre, loc="left", fontsize=10.5, color=C.ENCRE, fontweight="bold")
        ax.set_xlabel("Hectares", color=C.ENCRE_2)
    fig.suptitle("Artificialisation brute 2019-2022 : origine et destination des sols", x=0.03,
                 ha="left", fontsize=14, fontweight="bold", color=C.ENCRE, y=0.97)
    fig.text(0.03, 0.885, f"{config.EPCI_NOM} : {C.fr(art.surface_ha.sum(), 0, 'ha')} passés d'un état "
             "non artificialisé à artificialisé entre les millésimes 2019 et 2022", fontsize=9.5, color=C.ENCRE_2)
    fig.text(0.03, 0.025, "Source : IGN, OCS GE 2.0 différentiel 2019-2022 (Seine-Maritime) ; classement "
             f"selon le décret n° 2023-1096. Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig


# --- Cartes ---------------------------------------------------------------------------
SRC_OCS = "IGN, OCS GE 2.0 millésimes 2019 et 2022 et différentiel 2019-2022, ADMIN EXPRESS COG"


def carte_occupation(o22, com, perim, synth):
    fig, ax, axp = C.planche("Occupation du sol en 2022",
                             "Sept grandes classes issues de l'OCS GE (couverture × usage), "
                             "lecture « artificialisé / non artificialisé » du décret de 2023")
    C.fond_territoire(ax, com)
    simp = o22.dissolve("classe").reset_index()
    for k, (lib, coul) in CLASSES.items():
        simp[simp.classe == k].plot(ax=ax, color=coul, edgecolor="none", zorder=2, rasterized=True)
    C.surcouches(ax, com, None, perim)
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Chiffres clés 2022")
    P.chiffre(C.fr(synth["artif_2022_ha"], 0, "ha"),
              f"de surfaces artificialisées, soit {C.pct(synth['part_artif_2022'] * 100)} du territoire")
    P.chiffre(C.pct(synth["part_agri_2022"] * 100), "du territoire en espaces agricoles")
    P.chiffre(C.pct(synth["part_foret_2022"] * 100), "en forêts et boisements")
    P.espace(0.01)
    P.titre("Légende")
    P.texte("Surfaces artificialisées", taille=8.5, couleur=C.ENCRE)
    P.espace(0.004)
    for k in (1, 2, 3):
        P.case(CLASSES[k][1], CLASSES[k][0])
    P.espace(0.006)
    P.texte("Surfaces non artificialisées", taille=8.5, couleur=C.ENCRE)
    P.espace(0.004)
    for k in (4, 5, 6, 7):
        P.case(CLASSES[k][1], CLASSES[k][0])
    P.espace(0.01)
    P.titre("Lecture")
    P.texte("Le cœur urbain s'étire le long de la Seine, de Rouen à Elbeuf. Les forêts "
            "(Roumare, La Londe-Rouvray, Verte) et les plateaux agricoles de l'est et du nord "
            "forment une ceinture non artificialisée qui couvre près des deux tiers de la Métropole.",
            largeur=52)
    C.cartouche(fig, SRC_OCS)
    return fig


def carte_artificialisation(d, o22, com, perim, eau, synth):
    fig, ax, axp = C.planche("Artificialisation des sols entre 2019 et 2022",
                             "Changements détectés par l'IGN entre deux millésimes de l'OCS GE")
    C.fond_territoire(ax, com)
    o22[o22.artif].dissolve()[["geometry"]].plot(ax=ax, color="#dddcd6", edgecolor="none", zorder=2, rasterized=True)
    C.surcouches(ax, com, eau, perim)
    art = d[d.type_flux == "Artificialisation"]
    des = d[d.type_flux == "Désartificialisation"]
    # trait de contour épais pour rendre visibles des objets de quelques ares à l'échelle 1/100 000
    art.plot(ax=ax, color=C.ARTIF, edgecolor=C.ARTIF, linewidth=1.1, zorder=11)
    des.plot(ax=ax, color=C.DESARTIF, edgecolor=C.DESARTIF, linewidth=1.1, zorder=10)
    top = synth["top_communes"]
    lab = com[com.code_insee.isin(top.index)]
    for _, r in lab.iterrows():
        p = r.geometry.representative_point()
        ax.annotate(f"{r.nom}\n{C.fr(top[r.code_insee], 1, 'ha')} nets", (p.x, p.y), ha="center",
                    va="center", fontsize=7.5, color=C.ENCRE, fontweight="semibold", zorder=20,
                    path_effects=[C.pe.withStroke(linewidth=2.6, foreground="white")])
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Bilan 2019-2022")
    P.chiffre(C.fr(synth["artif_brute_ha"], 0, "ha"), "artificialisés (sols naturels, agricoles ou forestiers → artificialisés)",
              couleur=C.ARTIF)
    P.chiffre(C.fr(synth["desartif_ha"], 0, "ha"), "désartificialisés (renaturation, fin de chantier, friches revégétalisées)",
              couleur=C.DESARTIF)
    P.chiffre(C.fr(synth["artif_nette_ha"], 0, "ha"),
              f"d'artificialisation nette, soit environ {C.fr(synth['artif_nette_ha'] / 3, 0, 'ha')} par an")
    P.espace(0.01)
    P.titre("Légende")
    P.case(C.ARTIF, "Surface artificialisée entre 2019 et 2022")
    P.case(C.DESARTIF, "Surface désartificialisée entre 2019 et 2022")
    P.case("#dddcd6", "Surfaces déjà artificialisées en 2022")
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.01)
    P.titre("À retenir")
    P.texte("L'artificialisation nette mesurée par l'OCS GE ne se confond pas avec la consommation "
            "d'ENAF du Cerema : la première suit l'état des sols (un parc urbain reste "
            "non artificialisé), la seconde suit les parcelles qui deviennent urbanisées. "
            "La loi utilise la consommation d'ENAF jusqu'en 2031, puis l'artificialisation nette.",
            largeur=52)
    P.espace(0.01)
    P.texte("Contours des polygones grossis pour la lisibilité à cette échelle.", taille=7.5,
            couleur=C.ENCRE_3, largeur=60)
    C.cartouche(fig, SRC_OCS)
    return fig


def main():
    log("Étape 2 - OCS GE 2019-2022")
    com = lire("communes")
    perim = lire("perimetre")
    eau = fond_eau()
    o19, o22 = stocks(2019), stocks(2022)
    d = flux()

    # --- indicateurs communaux
    t = pd.DataFrame({"code_insee": com.code_insee})
    for an, o in ((2019, o19), (2022, o22)):
        g = o.groupby("code_insee")
        t = t.merge(g.apply(lambda x: x.loc[x.artif, "surface_ha"].sum(), include_groups=False)
                    .rename(f"artif_{an}_ha"), left_on="code_insee", right_index=True, how="left")
    t = t.merge(o22.groupby("code_insee").surface_ha.sum().rename("surface_ocs_ha"),
                left_on="code_insee", right_index=True, how="left")
    for lib, typ in (("artif_brute_1922_ha", "Artificialisation"), ("desartif_1922_ha", "Désartificialisation")):
        t = t.merge(d[d.type_flux == typ].groupby("code_insee").surface_ha.sum().rename(lib),
                    left_on="code_insee", right_index=True, how="left")
    t = t.fillna(0)
    t["artif_nette_1922_ha"] = t.artif_brute_1922_ha - t.desartif_1922_ha
    t["part_artif_2022_pct"] = t.artif_2022_ha / t.surface_ocs_ha * 100
    for k, (lib, _) in CLASSES.items():
        s = o22[o22.classe == k].groupby("code_insee").surface_ha.sum()
        t[f"ocs22_classe{k}_ha"] = t.code_insee.map(s).fillna(0)
    gdf = com[["code_insee", "nom", "geometry"]].merge(t, on="code_insee")
    ecrire(gdf, "ind_ocsge")

    # --- couches de travail
    o22_out = o22[["code_insee", "code_cs", "code_us", "artif", "classe", "geometry"]].copy()
    o22_out["libelle_classe"] = o22_out.classe.map(lambda k: CLASSES[k][0])
    ecrire(o22_out, "ocsge_2022_classee")
    flux_out = d[d.type_flux != "Changement sans effet"][
        ["code_insee", "cs_2019", "us_2019", "cs_2022", "us_2022", "classe_2019", "classe_2022",
         "type_flux", "surface_ha", "geometry"]]
    ecrire(flux_out, "ocsge_flux_2019_2022")

    # --- matrice de transition entre grandes classes (ha)
    mat = d.pivot_table(index="classe_2019", columns="classe_2022", values="surface_ha",
                        aggfunc="sum", fill_value=0)
    mat.index = [CLASSES[k][0] for k in mat.index]
    mat.columns = [CLASSES[k][0] for k in mat.columns]
    mat.round(2).to_csv(config.INTERIM / "matrice_transitions_ocsge_2019_2022.csv")

    tot = o22.surface_ha.sum()
    synth = {
        "artif_2019_ha": o19.loc[o19.artif, "surface_ha"].sum(),
        "artif_2022_ha": o22.loc[o22.artif, "surface_ha"].sum(),
        "part_artif_2022": o22.loc[o22.artif, "surface_ha"].sum() / tot,
        "part_agri_2022": o22.loc[o22.classe == 4, "surface_ha"].sum() / tot,
        "part_foret_2022": o22.loc[o22.classe == 6, "surface_ha"].sum() / tot,
        "artif_brute_ha": t.artif_brute_1922_ha.sum(),
        "desartif_ha": t.desartif_1922_ha.sum(),
    }
    synth["artif_nette_ha"] = synth["artif_brute_ha"] - synth["desartif_ha"]
    # comparaison avec la consommation d'ENAF Cerema sur les flux 2019, 2020, 2021
    cerema = pd.read_csv(config.RAW / "conso_com.csv", low_memory=False, dtype={"epci25": str})
    cerema = cerema[cerema.epci25 == config.EPCI_SIREN]
    synth["conso_enaf_2019_2021_ha"] = (cerema.naf19art20 + cerema.naf20art21 + cerema.naf21art22).sum() / 1e4
    synth_top = t.set_index("code_insee").artif_nette_1922_ha.nlargest(6)
    synth["top_communes"] = synth_top

    G = config.LIVRABLES / "04_Graphiques"
    fig = graphique_flux(d)
    fig.savefig(G / "G04_Origine_destination_artificialisation_2019-2022.png", dpi=200, facecolor="white")
    fig.savefig(G / "G04_Origine_destination_artificialisation_2019-2022.pdf", facecolor="white")
    plt.close(fig)
    C.enregistrer(carte_occupation(o22, com, perim, synth), "C03_Occupation_du_sol_2022")
    C.enregistrer(carte_artificialisation(d, o22, com, perim, eau, synth), "C04_Artificialisation_2019-2022")

    out = {k: v for k, v in synth.items() if k != "top_communes"}
    pd.Series(out).to_json(config.INTERIM / "synthese_etape2.json", indent=1)
    for k, v in out.items():
        log(f"  {k:26s} {v:,.1f}")
    log("Étape 2 terminée")


if __name__ == "__main__":
    main()
