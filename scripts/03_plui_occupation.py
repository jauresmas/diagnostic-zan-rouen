"""Étape 3 - Croisement du zonage du PLUi avec l'occupation réelle du sol.

Questions traitées :
  - Quelle part des zones à urbaniser (AU) est encore non artificialisée ?
    C'est le « réservoir » de consommation future d'ENAF inscrit au PLUi.
  - Combien d'hectares agricoles déclarés à la PAC (RPG 2024) sont en zone U ou AU ?
  - Combien de surfaces non artificialisées subsistent dans les zones urbaines (U) ?
  - Ce réservoir est-il compatible avec l'enveloppe ZAN restante d'ici 2031 ?
"""
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import cartes as C
import config
from outils import ecrire, fond_eau, lire, log


def type_simplifie(typezone):
    return "AU" if str(typezone).startswith("AU") else str(typezone)


def vocation_au(libelle):
    lib = str(libelle).upper()
    if lib.startswith("2AU") and "X" not in lib:
        return "Habitat / mixte (2AU, fermée)"
    if "X" in lib:
        return "Activités économiques"
    if lib.startswith("1AUL"):
        return "Loisirs et équipements"
    return "Habitat / mixte"


VOCATIONS = {
    "Habitat / mixte": C.DESTINATIONS["hab"][1],
    "Habitat / mixte (2AU, fermée)": "#f3b49b",
    "Activités économiques": C.DESTINATIONS["act"][1],
    "Loisirs et équipements": C.DESTINATIONS["mix"][1],
}


def preparer_zones():
    z = lire("plui_zonage")
    z["geometry"] = z.geometry.make_valid()
    z = z[z.geometry.area > 0].reset_index(drop=True)
    z["id_zone"] = np.arange(len(z))
    z["famille"] = z.typezone.map(type_simplifie)
    z["ouverture"] = np.where(z.typezone == "AUs", "fermée (2AU)",
                              np.where(z.typezone == "AUc", "ouverte (1AU)", ""))
    z["vocation"] = np.where(z.famille == "AU", z.libelle.map(vocation_au), "")
    z["surface_ha"] = z.area / 1e4
    return z


def croiser(z, ocs, rpg):
    log("  croisement zonage x OCS GE 2022")
    x = gpd.overlay(z[["id_zone", "geometry"]], ocs[["artif", "classe", "geometry"]],
                    how="intersection", keep_geom_type=True)
    x["ha"] = x.area / 1e4
    st = x.pivot_table(index="id_zone", columns="artif", values="ha", aggfunc="sum", fill_value=0)
    st = st.rename(columns={True: "artif_ha", False: "non_artif_ha"})
    agri = x[x.classe == 4].groupby("id_zone").ha.sum().rename("agri_ocs_ha")
    log("  croisement zonage x RPG 2024")
    r = gpd.overlay(z[["id_zone", "geometry"]], rpg[["geometry"]], how="intersection",
                    keep_geom_type=True)
    rpg_ha = (r.area / 1e4).groupby(r.id_zone).sum().rename("rpg_ha")
    z = z.merge(st, left_on="id_zone", right_index=True, how="left")
    z = z.merge(agri, left_on="id_zone", right_index=True, how="left")
    z = z.merge(rpg_ha, left_on="id_zone", right_index=True, how="left")
    for c in ("artif_ha", "non_artif_ha", "agri_ocs_ha", "rpg_ha"):
        z[c] = z[c].fillna(0)
    z["part_non_artif_pct"] = z.non_artif_ha / z.surface_ha * 100
    return z, x


# --- Graphique : réservoir AU vs enveloppe ZAN ------------------------------------------
def graphique_reservoir(z, synth1):
    au = z[z.famille == "AU"]
    par_voc = au.groupby("vocation").non_artif_ha.sum().reindex(list(VOCATIONS), fill_value=0)
    restant = synth1["enveloppe_zan_ha"] - synth1["conso_2125_ha"]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    fig.subplots_adjust(left=0.24, right=0.93, top=0.68, bottom=0.16)
    gauche = 0
    for voc, coul in VOCATIONS.items():
        v = par_voc[voc]
        if v <= 0:
            continue
        ax.barh(1, v, left=gauche, height=0.5, color=coul, edgecolor="white", lw=1.5, label=voc)
        if v > 25:
            ax.text(gauche + v / 2, 1, C.fr(v, 0, "ha"), ha="center", va="center", fontsize=8.5,
                    color="white" if coul in (C.DESTINATIONS["act"][1], C.DESTINATIONS["hab"][1]) else C.ENCRE)
        gauche += v
    ax.text(gauche + 8, 1, C.fr(gauche, 0, "ha"), va="center", fontsize=10, fontweight="bold", color=C.ENCRE)
    ax.barh(0, restant, height=0.5, color=C.ACCENT, edgecolor="white")
    ax.text(restant + 8, 0, C.fr(restant, 0, "ha"), va="center", fontsize=10, fontweight="bold", color=C.ACCENT)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Enveloppe ZAN restante\n1er janv. 2025 → 2031", "Zones AU du PLUi\nnon artificialisées (2022)"],
                       fontsize=9.5, color=C.ENCRE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C.AXE)
    ax.xaxis.grid(True, color=C.GRILLE, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_xlabel("Hectares", color=C.ENCRE_2)
    ax.set_xlim(0, max(gauche, restant) * 1.12)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.04), ncol=4, frameon=False, fontsize=8.5,
              handlelength=1.2, columnspacing=1.4)
    ratio = gauche / restant
    fig.suptitle("Le réservoir foncier du PLUi face à l'enveloppe ZAN", x=0.03, ha="left",
                 fontsize=14, fontweight="bold", color=C.ENCRE, y=0.965)
    fig.text(0.03, 0.865, f"Les zones à urbaniser encore non artificialisées représentent {C.fr(ratio, 1)} fois "
             "l'enveloppe de consommation restante jusqu'en 2031", fontsize=9.5, color=C.ENCRE_2)
    fig.text(0.03, 0.03, "Sources : Géoportail de l'Urbanisme (PLUi approuvé le 04/05/2026), IGN OCS GE 2022, "
             f"Cerema 2011-2025. Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig, restant


# --- Cartes ------------------------------------------------------------------------------
SRC_PLUI = ("Géoportail de l'Urbanisme, PLUi de la Métropole Rouen Normandie approuvé le 04/05/2026 ; "
            "IGN, OCS GE 2022, ADMIN EXPRESS COG ; ASP, RPG 2024")


def carte_zonage(z, com, perim, eau, synth):
    fig, ax, axp = C.planche("Zonage simplifié du PLUi",
                             "Regroupement des 4 grandes familles de zones du règlement graphique")
    C.fond_territoire(ax, com)
    for t, (lib, coul) in C.ZONES.items():
        sel = z[z.famille == t]
        if t == "AU":
            sel.plot(ax=ax, facecolor=coul, edgecolor="white", hatch="////", linewidth=0.0, zorder=3)
        else:
            sel.plot(ax=ax, color=coul, edgecolor="none", zorder=2, rasterized=True)
    C.surcouches(ax, com, eau, perim)
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Répartition du territoire")
    tot = z.surface_ha.sum()
    for t in ("U", "AU", "A", "N"):
        s = z.loc[z.famille == t, "surface_ha"].sum()
        P.case(C.ZONES[t][1], f"{C.ZONES[t][0]} : {C.fr(s, 0, 'ha')} ({C.pct(s / tot * 100)})",
               hachure="////" if t == "AU" else None)
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.015)
    P.titre("Chiffres clés")
    P.chiffre(C.fr(synth["au_total_ha"], 0, "ha"),
              f"de zones à urbaniser, dont {C.fr(synth['au_ouvertes_ha'], 0, 'ha')} ouvertes (1AU) "
              f"et {C.fr(synth['au_fermees_ha'], 0, 'ha')} fermées (2AU)")
    P.chiffre(C.fr(synth["u_non_artif_ha"], 0, "ha"),
              "non artificialisés à l'intérieur des zones urbaines (jardins, parcs, terrains libres)")
    P.espace(0.01)
    P.titre("Lecture")
    P.texte("Les zones naturelles et agricoles couvrent près des trois quarts de la Métropole. "
            "Les zones à urbaniser, peu étendues en surface, concentrent pourtant l'essentiel "
            "de la consommation d'ENAF à venir.", largeur=52)
    C.cartouche(fig, SRC_PLUI)
    return fig


def carte_reservoir(z, x, com, perim, eau, synth):
    fig, ax, axp = C.planche("Le réservoir foncier des zones à urbaniser",
                             "Zones AU du PLUi selon leur vocation et l'état des sols en 2022 (OCS GE)")
    C.fond_territoire(ax, com)
    z[z.famille == "U"].dissolve()[["geometry"]].plot(ax=ax, color="#e9e6e0", edgecolor="none", zorder=2)
    au = z[z.famille == "AU"]
    for voc, coul in VOCATIONS.items():
        sel = au[au.vocation == voc]
        if not sel.empty:  # contour épais de même teinte : zones lisibles au 1/100 000
            sel.plot(ax=ax, color=coul, edgecolor=coul, linewidth=1.4, zorder=3)
    # parties déjà artificialisées des zones AU : trame grise par-dessus
    deja = x[(x.id_zone.isin(au.id_zone)) & (x.artif)]
    if not deja.empty:
        deja.plot(ax=ax, facecolor="none", edgecolor="#3a3a3a", hatch="xxxx", linewidth=0, zorder=4)
    au.boundary.plot(ax=ax, color=C.ENCRE, linewidth=0.5, zorder=5)
    C.surcouches(ax, com, eau, perim)
    top = synth["top_communes_au"]
    noms = com.set_index("code_insee").nom
    for insee, val in top.items():
        p = au[au.code_insee == insee].union_all().centroid  # étiquette au plus près des zones AU
        ax.annotate(f"{noms[insee]}\n{C.fr(val, 0, 'ha')}", (p.x, p.y), xytext=(0, 14),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=7.5, color=C.ENCRE, fontweight="semibold", zorder=20,
                    arrowprops=dict(arrowstyle="-", color=C.ENCRE_2, lw=0.6),
                    path_effects=[C.pe.withStroke(linewidth=2.6, foreground="white")])
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Chiffres clés")
    P.chiffre(C.fr(synth["au_non_artif_ha"], 0, "ha"),
              f"de zones AU encore non artificialisées en 2022 ({C.pct(synth['au_non_artif_ha'] / synth['au_total_ha'] * 100)} des zones AU)",
              couleur=C.ARTIF)
    P.chiffre(C.fr(synth["au_rpg_ha"], 0, "ha"), "de parcelles agricoles déclarées à la PAC (RPG 2024) en zone AU")
    P.chiffre(C.fr(synth["enveloppe_restante_ha"], 0, "ha"),
              "d'enveloppe ZAN restante entre 2025 et 2031 (indicatif)", couleur=C.ACCENT)
    P.espace(0.01)
    P.titre("Légende")
    P.texte("Zones à urbaniser, par vocation", taille=8.5, couleur=C.ENCRE)
    P.espace(0.004)
    for voc, coul in VOCATIONS.items():
        P.case(coul, voc)
    P.case("white", "Partie déjà artificialisée en 2022", hachure="xxxx", bord="#3a3a3a")
    P.case("#e9e6e0", "Zones urbaines (U)")
    P.espace(0.01)
    P.titre("Lecture")
    P.texte("Étiquettes : surface AU non artificialisée par commune (6 premières). Toutes les zones AU "
            "ne seront pas urbanisées d'ici 2031 : les zones 2AU doivent d'abord être ouvertes "
            "par une procédure d'évolution du PLUi. Une partie des zones ouvertes a aussi été "
            "aménagée après 2022 (ZAC en cours).", largeur=52)
    C.cartouche(fig, SRC_PLUI)
    return fig


def main():
    log("Étape 3 - PLUi x occupation du sol")
    com, perim, eau = lire("communes"), lire("perimetre"), fond_eau()
    ocs = lire("ocsge_2022_classee")
    rpg = lire("rpg_2024")
    z = preparer_zones()
    z, x = croiser(z, ocs, rpg)
    ecrire(z, "plui_zonage_qualifie")
    au = z[z.famille == "AU"]
    ecrire(au, "plui_zones_au")

    synth1 = json.loads((config.INTERIM / "synthese_etape1.json").read_text(encoding="utf-8"))
    par_type = z.groupby("famille")[["surface_ha", "artif_ha", "non_artif_ha", "rpg_ha"]].sum()
    synth = {
        "au_total_ha": au.surface_ha.sum(),
        "au_ouvertes_ha": au.loc[au.typezone == "AUc", "surface_ha"].sum(),
        "au_fermees_ha": au.loc[au.typezone == "AUs", "surface_ha"].sum(),
        "au_non_artif_ha": au.non_artif_ha.sum(),
        "au_non_artif_habitat_ha": au.loc[au.vocation.str.startswith("Habitat"), "non_artif_ha"].sum(),
        "au_non_artif_activites_ha": au.loc[au.vocation == "Activités économiques", "non_artif_ha"].sum(),
        "au_rpg_ha": au.rpg_ha.sum(),
        "u_total_ha": par_type.loc["U", "surface_ha"],
        "u_non_artif_ha": par_type.loc["U", "non_artif_ha"],
        "u_rpg_ha": par_type.loc["U", "rpg_ha"],
        "an_artif_ha": par_type.loc[["A", "N"], "artif_ha"].sum(),
        "enveloppe_restante_ha": synth1["enveloppe_zan_ha"] - synth1["conso_2125_ha"],
    }
    par_com = au.groupby("code_insee").non_artif_ha.sum()
    synth["top_communes_au"] = par_com.nlargest(6)

    # indicateurs communaux
    t = z.pivot_table(index="code_insee", columns="famille", values="surface_ha", aggfunc="sum", fill_value=0)
    t.columns = [f"zone_{c}_ha" for c in t.columns]
    t["au_non_artif_ha"] = par_com
    t["au_rpg_ha"] = au.groupby("code_insee").rpg_ha.sum()
    t["u_non_artif_ha"] = z[z.famille == "U"].groupby("code_insee").non_artif_ha.sum()
    t = t.fillna(0).reset_index()
    ecrire(com[["code_insee", "nom", "geometry"]].merge(t, on="code_insee", how="left").fillna(0), "ind_plui")

    G = config.LIVRABLES / "04_Graphiques"
    fig, _ = graphique_reservoir(z, synth1)
    fig.savefig(G / "G05_Reservoir_AU_vs_enveloppe_ZAN.png", dpi=200, facecolor="white")
    fig.savefig(G / "G05_Reservoir_AU_vs_enveloppe_ZAN.pdf", facecolor="white")
    plt.close(fig)
    C.enregistrer(carte_zonage(z, com, perim, eau, synth), "C05_Zonage_PLUi_simplifie")
    C.enregistrer(carte_reservoir(z, x, com, perim, eau, synth), "C06_Reservoir_foncier_zones_AU")

    out = {k: v for k, v in synth.items() if k != "top_communes_au"}
    pd.Series(out).to_json(config.INTERIM / "synthese_etape3.json", indent=1)
    for k, v in out.items():
        log(f"  {k:28s} {v:,.1f}")
    log("Étape 3 terminée")


if __name__ == "__main__":
    main()
