"""Étape 1 - Consommation d'espaces naturels, agricoles et forestiers (ENAF).

Source : Cerema, fichiers fonciers, flux annuels du 1er janvier 2011 au
1er janvier 2025 (millésime 2025). Valeurs en m² converties en hectares.

Indicateurs produits par commune :
  - consommation 2011-2021 (période de référence ZAN) et 2021-2025, par destination
  - rythme annuel moyen et évolution entre les deux périodes
  - enveloppe indicative 2021-2031 (-50 %) et part déjà consommée
  - efficacité foncière : m² consommés pour l'habitat par ménage supplémentaire
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Ellipse

import cartes as C
import config
from outils import ecrire, fond_eau, lire, log

ANNEES = list(range(2011, 2025))  # flux du 1er janvier n au 1er janvier n+1
DEST = {"hab": ["hab"], "act": ["act"], "mix": ["mix"], "inf": ["rou", "fer"], "inc": ["inc"]}


def charger():
    d = pd.read_csv(config.RAW / "conso_com.csv", low_memory=False,
                    dtype={"idcom": str, "epci25": str, "iddep": str})
    return d[d.epci25 == config.EPCI_SIREN].copy()


def serie_annuelle(d):
    lignes = []
    for a in ANNEES:
        y0, y1 = f"{a % 100:02d}", f"{(a + 1) % 100:02d}"
        ligne = {"annee": a, "total_ha": d[f"naf{y0}art{y1}"].sum() / 1e4}
        for k, suff in DEST.items():
            ligne[f"{k}_ha"] = sum(d[f"art{y0}{s}{y1}"].sum() for s in suff) / 1e4
        lignes.append(ligne)
    s = pd.DataFrame(lignes)
    ecart = (s[[f"{k}_ha" for k in DEST]].sum(axis=1) - s.total_ha).abs().max()
    assert ecart < 0.01, f"somme des destinations != total ({ecart})"
    return s


def indicateurs(d):
    t = pd.DataFrame({"code_insee": d.idcom.values, "nom": d.idcomtxt.values})
    v = lambda col: d[col].to_numpy(dtype=float)  # noqa: E731
    for per, (a, b) in {"1121": ("11", "21"), "2125": ("21", "25"), "1125": ("11", "25")}.items():
        t[f"conso_{per}_ha"] = v(f"naf{a}art{b}") / 1e4
        for k, suff in DEST.items():
            t[f"c{per}_{k}_ha"] = sum(v(f"art{a}{s}{b}") for s in suff) / 1e4
    t["moy_an_1121_ha"] = t.conso_1121_ha / 10
    t["moy_an_2125_ha"] = t.conso_2125_ha / 4
    with np.errstate(divide="ignore", invalid="ignore"):
        t["evol_rythme_pct"] = np.where(t.moy_an_1121_ha > 0,
                                        (t.moy_an_2125_ha / t.moy_an_1121_ha - 1) * 100, np.nan)
        t["enveloppe_zan_ha"] = t.conso_1121_ha * (1 - config.TAUX_REDUCTION)
        t["part_enveloppe_pct"] = np.where(t.enveloppe_zan_ha > 0,
                                           t.conso_2125_ha / t.enveloppe_zan_ha * 100, np.nan)
        t["projection_2131_ha"] = t.moy_an_2125_ha * 10
        t["surface_com_ha"] = v("surfcom2025") / 1e4
        t["part_surface_conso_1125_pct"] = t.conso_1125_ha / t.surface_com_ha * 100
        t["pop_2011"], t["pop_2022"] = v("pop11"), v("pop22")
        t["men_2011"], t["men_2022"] = v("men11"), v("men22")
        t["emp_2011"], t["emp_2022"] = v("emp11"), v("emp22")
        dmen = t.men_2022 - t.men_2011
        t["m2_hab_par_menage_1122"] = np.where(dmen > 0, v("art11hab22") / dmen, np.nan)
    # dominante de la consommation 2011-2021
    cols = [f"c1121_{k}_ha" for k in DEST]
    t["dominante_1121"] = t[cols].idxmax(axis=1).str.extract(r"c1121_(\w+)_ha")[0]
    t.loc[t.conso_1121_ha == 0, "dominante_1121"] = None
    t["classe_effort"] = t.apply(classe_effort, axis=1)
    return t


CLASSES_EFFORT = [
    "Réduction d'au moins 50 %",
    "Réduction de moins de 50 %",
    "Hausse jusqu'à +50 %",
    "Hausse de plus de 50 %",
]
CLASSE_MARGINALE = "Consommation marginale (< 1 ha en 2011-2021)"


def classe_effort(r):
    if r.conso_1121_ha < 1:
        return CLASSE_MARGINALE
    e = r.evol_rythme_pct
    if e <= -50:
        return CLASSES_EFFORT[0]
    if e <= 0:
        return CLASSES_EFFORT[1]
    if e <= 50:
        return CLASSES_EFFORT[2]
    return CLASSES_EFFORT[3]


# --- Graphiques ------------------------------------------------------------------
def style_axe(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C.AXE)
    ax.yaxis.grid(True, color=C.GRILLE, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def graphique_annuel(s, synthese):
    fig, ax = plt.subplots(figsize=(11, 5.6))
    fig.subplots_adjust(left=0.07, right=0.84, top=0.80, bottom=0.12)
    bas = np.zeros(len(s))
    for k, (lib, coul) in C.DESTINATIONS.items():
        ax.bar(s.annee, s[f"{k}_ha"], bottom=bas, width=0.62, color=coul, label=lib,
               edgecolor="white", linewidth=1.2)
        bas += s[f"{k}_ha"].to_numpy()
    moy_ref = synthese["moy_an_1121_ha"]
    cible = moy_ref * (1 - config.TAUX_REDUCTION)
    ax.axhline(moy_ref, color=C.ENCRE_2, lw=1, ls=(0, (4, 3)))
    ax.axhline(cible, color=C.ACCENT, lw=1.6, ls=(0, (4, 3)))
    ax.text(2024.55, moy_ref, f"Moyenne 2011-2021\n{C.fr(moy_ref, 1, 'ha/an')}", va="center", fontsize=8.5,
            color=C.ENCRE_2)
    ax.text(2024.55, cible, f"Rythme cible ZAN\n{C.fr(cible, 1, 'ha/an')}", va="center", fontsize=8.5,
            color=C.ACCENT, fontweight="bold")
    ax.axvline(2020.5, color=C.AXE, lw=0.8)
    ax.text(2020.6, ax.get_ylim()[1] * 0.97, "Période ZAN 2021-2031 →", fontsize=8.5,
            color=C.ENCRE_2, va="top")
    for x, y in zip(s.annee, s.total_ha):
        ax.text(x, y + 0.8, f"{y:.0f}", ha="center", va="bottom", fontsize=8, color=C.ENCRE_2)
    style_axe(ax)
    ax.set_xticks(ANNEES)
    ax.set_xlim(2010.4, 2024.6)
    ax.set_ylabel("Hectares d'ENAF consommés", color=C.ENCRE_2)
    fig.suptitle("Consommation annuelle d'ENAF par destination, 2011-2024", x=0.07, ha="left",
                 fontsize=14, fontweight="bold", color=C.ENCRE, y=0.965)
    fig.text(0.07, 0.885, f"{config.EPCI_NOM}, flux du 1er janvier de l'année n au 1er janvier n+1",
             fontsize=9.5, color=C.ENCRE_2)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=5, frameon=False, fontsize=8.5,
              handlelength=1.2, columnspacing=1.6)
    fig.text(0.07, 0.03, "Source : Cerema, consommation d'ENAF 2011-2025 (fichiers fonciers). "
             f"Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig


def graphique_trajectoire(s, synthese):
    env = synthese["enveloppe_zan_ha"]
    cumul = s[s.annee >= 2021].total_ha.cumsum().to_numpy()
    x_obs = np.array([2021, 2022, 2023, 2024, 2025])
    y_obs = np.concatenate([[0], cumul])
    rythme = cumul[-1] / 4
    x_proj = np.arange(2025, 2032)
    y_proj = cumul[-1] + rythme * (x_proj - 2025)
    fig, ax = plt.subplots(figsize=(11, 5.6))
    fig.subplots_adjust(left=0.07, right=0.80, top=0.84, bottom=0.12)
    ax.plot([2021, 2031], [0, env], color=C.ACCENT, lw=2, ls=(0, (4, 3)))
    ax.axhline(env, color=C.ACCENT, lw=0.8)
    ax.plot(x_obs, y_obs, color=C.ARTIF, lw=2.4, marker="o", ms=7,
            markeredgecolor="white", markeredgewidth=1.5, zorder=5)
    ax.plot(x_proj, y_proj, color=C.ARTIF, lw=2, ls=(0, (1.5, 2)), zorder=4)
    annee_dep = 2025 + (env - cumul[-1]) / rythme if rythme > 0 else None
    style_axe(ax)
    ax.set_xlim(2020.6, 2031.4)
    ax.set_ylim(0, max(y_proj.max(), env) * 1.12)
    ax.set_xticks(range(2021, 2032))
    ax.set_xticklabels([f"1er janv.\n{a}" if a in (2021, 2025, 2031) else str(a) for a in range(2021, 2032)])
    ax.set_ylabel("Consommation cumulée depuis 2021 (ha)", color=C.ENCRE_2)
    ax.text(2031.25, env, f"Enveloppe 2021-2031\n{C.fr(env, 0, 'ha')}", va="center", ha="left", fontsize=9,
            color=C.ACCENT, fontweight="bold", clip_on=False)
    ax.text(2031.25, y_proj[-1], f"Au rythme actuel\n{C.fr(y_proj[-1], 0, 'ha')} en 2031", va="center",
            ha="left", fontsize=9, color=C.ARTIF, fontweight="bold", clip_on=False)
    ax.annotate(f"{C.fr(cumul[-1], 0, 'ha')} consommés\nau 1er janvier 2025\n"
                f"({C.pct(cumul[-1] / env * 100)} de l'enveloppe)",
                (2025, cumul[-1]), xytext=(2025.3, cumul[-1] * 0.45), fontsize=9, color=C.ENCRE,
                arrowprops=dict(arrowstyle="-", color=C.ENCRE_3, lw=0.8))
    if annee_dep and annee_dep < 2031:
        ax.axvline(annee_dep, color=C.ENCRE_3, lw=0.8, ls=":")
        moment = ("début ", "mi-", "fin ")[min(2, int((annee_dep % 1) * 3))]
        ax.text(annee_dep - 0.1, ax.get_ylim()[1] * 0.98,
                f"Enveloppe épuisée\n{moment}{int(annee_dep)}",
                ha="right", va="top", fontsize=8.5, color=C.ENCRE_2)
    leg = [Line2D([], [], color=C.ARTIF, lw=2.4, marker="o", label="Consommation observée"),
           Line2D([], [], color=C.ARTIF, lw=2, ls=(0, (1.5, 2)),
                  label="Projection au rythme 2021-2024"),
           Line2D([], [], color=C.ACCENT, lw=2, ls=(0, (4, 3)), label="Trajectoire linéaire -50 %")]
    ax.legend(handles=leg, loc="upper left", frameon=False, fontsize=8.5)
    fig.suptitle("Trajectoire ZAN : consommation cumulée depuis le 1er janvier 2021", x=0.07,
                 ha="left", fontsize=14, fontweight="bold", color=C.ENCRE, y=0.965)
    fig.text(0.07, 0.885, "Enveloppe indicative = 50 % de la consommation 2011-2021 "
             "(loi Climat et Résilience, avant territorialisation SRADDET / SCoT)",
             fontsize=9.5, color=C.ENCRE_2)
    fig.text(0.07, 0.03, "Source : Cerema, consommation d'ENAF 2011-2025 (fichiers fonciers). "
             f"Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig, annee_dep


def graphique_top(t, n=15):
    top = t.nlargest(n, "conso_1121_ha").iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 6.2))
    fig.subplots_adjust(left=0.20, right=0.92, top=0.82, bottom=0.12)
    gauche = np.zeros(len(top))
    for k, (lib, coul) in C.DESTINATIONS.items():
        ax.barh(top.nom, top[f"c1121_{k}_ha"], left=gauche, height=0.66, color=coul, label=lib,
                edgecolor="white", linewidth=1.2)
        gauche += top[f"c1121_{k}_ha"].to_numpy()
    for y, (tot, rec) in enumerate(zip(top.conso_1121_ha, top.conso_2125_ha)):
        ax.text(tot + 0.6, y, C.fr(tot, 1, "ha"), va="center", fontsize=8.5, color=C.ENCRE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C.AXE)
    ax.xaxis.grid(True, color=C.GRILLE, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_xlabel("Hectares d'ENAF consommés entre 2011 et 2021", color=C.ENCRE_2)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=5, frameon=False, fontsize=8.5,
              handlelength=1.2, columnspacing=1.6)
    fig.suptitle(f"Les {n} communes les plus consommatrices d'ENAF, 2011-2021", x=0.07, ha="left",
                 fontsize=14, fontweight="bold", color=C.ENCRE, y=0.965)
    part = top.conso_1121_ha.sum() / t.conso_1121_ha.sum()
    fig.text(0.07, 0.905, f"Elles représentent {C.pct(part * 100)} de la consommation de la Métropole "
             f"({len(t)} communes)", fontsize=9.5, color=C.ENCRE_2)
    fig.text(0.07, 0.02, "Source : Cerema, consommation d'ENAF 2011-2025 (fichiers fonciers). "
             f"Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig


# --- Cartes ----------------------------------------------------------------------
SRC_CEREMA = ("Cerema, consommation d'ENAF 2011-2025 (fichiers fonciers) ; IGN, ADMIN EXPRESS COG, "
              "OCS GE 2022 (surfaces en eau)")


def carte_consommation(gdf, synthese, eau, perim):
    fig, ax, axp = C.planche(
        "Consommation d'espaces naturels, agricoles et forestiers",
        "Période de référence de la loi Climat et Résilience : 1er janvier 2011 - 1er janvier 2021")
    C.fond_territoire(ax, gdf)
    gdf.plot(ax=ax, color="#f6f5f1", edgecolor="none", zorder=1)
    C.surcouches(ax, gdf, eau, perim)
    vmax = gdf.conso_1121_ha.max()
    rmax = 2300  # rayon (m) du plus grand cercle
    pts = gdf.copy()
    pts["geometry"] = pts.geometry.representative_point()
    pts = pts[pts.conso_1121_ha > 0].sort_values("conso_1121_ha", ascending=False)
    for _, r in pts.iterrows():
        rayon = rmax * np.sqrt(r.conso_1121_ha / vmax)
        coul = C.DESTINATIONS[r.dominante_1121][1]
        ax.add_patch(Circle((r.geometry.x, r.geometry.y), rayon, facecolor=coul, alpha=0.88,
                            edgecolor="white", lw=1.0, zorder=10))
    # étiquettes : communes les plus consommatrices + Rouen, centrées sur le cercle
    lab = gdf[(gdf.conso_1121_ha >= 14) | (gdf.nom == "Rouen")]
    for _, r in lab.iterrows():
        p = r.geometry.representative_point()
        ax.annotate(f"{r.nom}\n{C.fr(r.conso_1121_ha, 0, 'ha')}", (p.x, p.y), ha="center", va="center",
                    fontsize=7.5, color=C.ENCRE, fontweight="semibold", zorder=20,
                    path_effects=[C.pe.withStroke(linewidth=2.6, foreground="white")])
    C.echelle_nord(ax)
    # panneau
    P = C.Panneau(axp)
    P.titre("Chiffres clés")
    P.chiffre(C.fr(synthese["conso_1121_ha"], 0, "ha"), "d'ENAF consommés entre 2011 et 2021")
    P.chiffre(C.fr(synthese["moy_an_1121_ha"], 1, "ha / an"),
              f"en moyenne, soit environ {synthese['moy_an_1121_ha'] / 0.714:.0f} terrains de football par an")
    P.chiffre(C.pct(synthese["part_hab_1121"] * 100), "de la consommation est destinée à l'habitat")
    P.espace(0.01)
    P.titre("Légende")
    P.texte("Consommation 2011-2021 (ha)", taille=8.5, couleur=C.ENCRE)
    P.espace(0.005)
    # cercles de légende dans le panneau, à la même échelle que la carte
    x0, x1 = ax.get_xlim()
    pos_c, pos_p = ax.get_position(), axp.get_position()
    ech = (pos_c.width / (x1 - x0)) / pos_p.width  # mètres -> unités x du panneau
    ratio = (pos_p.height * C.A3_PAYSAGE[1]) / (pos_p.width * C.A3_PAYSAGE[0])
    r_max_leg = rmax * np.sqrt(80 / vmax) * ech
    cx, base = 0.02 + r_max_leg, P.y - 2 * r_max_leg / ratio - 0.005
    for val in (80, 40, 10):
        r = rmax * np.sqrt(val / vmax) * ech
        axp.add_patch(Ellipse((cx, base + r / ratio), 2 * r, 2 * r / ratio,
                              facecolor="none", edgecolor=C.ENCRE_2, lw=0.8))
        axp.plot([cx, cx + r_max_leg + 0.04], [base + 2 * r / ratio] * 2, color=C.ENCRE_3, lw=0.5)
        axp.text(cx + r_max_leg + 0.05, base + 2 * r / ratio, f"{val} ha", va="center", fontsize=8,
                 color=C.ENCRE)
    P.y = base - 0.025
    P.texte("Destination dominante", taille=8.5, couleur=C.ENCRE)
    P.espace(0.004)
    for k in ("hab", "act", "mix", "inf", "inc"):
        if (gdf.dominante_1121 == k).any():
            P.case(C.DESTINATIONS[k][1], C.DESTINATIONS[k][0])
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.01)
    P.titre("Lecture")
    P.texte(
        "Le plateau nord (Isneauville, Bois-Guillaume) et la rive gauche industrielle "
        "(Grand-Couronne) concentrent l'essentiel des surfaces consommées. "
        "La surface des cercles est proportionnelle aux hectares consommés.",
        largeur=52)
    C.cartouche(fig, SRC_CEREMA)
    return fig


def carte_effort(gdf, synthese, eau, perim):
    fig, ax, axp = C.planche(
        "Rythme de consommation depuis 2021 : où en est la sobriété foncière ?",
        "Évolution du rythme annuel moyen 2021-2024 par rapport à 2011-2020 (objectif national : -50 %)")
    C.fond_territoire(ax, gdf)
    couleurs = dict(zip(CLASSES_EFFORT, C.DIVERGENT)) | {CLASSE_MARGINALE: C.NEUTRE}
    gdf.plot(ax=ax, color=gdf.classe_effort.map(couleurs), edgecolor="none", zorder=1)
    C.surcouches(ax, gdf, eau, perim)
    lab = gdf[(gdf.conso_1121_ha >= 12) | (gdf.nom == "Rouen")]
    for _, r in lab.iterrows():
        p = r.geometry.representative_point()
        ev = C.pct(r.evol_rythme_pct, signe=True)
        ax.annotate(f"{r.nom}\n{ev}", (p.x, p.y), ha="center", va="center", fontsize=7.5,
                    color=C.ENCRE, zorder=20, path_effects=[C.pe.withStroke(linewidth=2.4, foreground="white")])
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Bilan à l'échelle de la Métropole")
    P.chiffre(C.fr(synthese["conso_2125_ha"], 0, "ha"), "consommés entre le 1er janvier 2021 et le 1er janvier 2025")
    P.chiffre(C.pct(synthese["part_enveloppe"] * 100),
              f"de l'enveloppe indicative 2021-2031 ({C.fr(synthese['enveloppe_zan_ha'], 0, 'ha')}) "
              "utilisés en 4 ans sur 10",
              couleur=C.DIVERGENT[3] if synthese["part_enveloppe"] > 0.4 else C.DIVERGENT[0])
    P.chiffre(C.pct(synthese["evol_rythme_pct"], signe=True),
              "d'évolution du rythme annuel (objectif : −50 %)")
    P.espace(0.01)
    P.titre("Légende")
    for cl in CLASSES_EFFORT:
        n = (gdf.classe_effort == cl).sum()
        P.case(couleurs[cl], f"{cl} ({n})")
    P.case(C.NEUTRE, f"{CLASSE_MARGINALE} ({(gdf.classe_effort == CLASSE_MARGINALE).sum()})")
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.01)
    P.titre("Méthode et limites")
    P.texte(
        "Rythme 2021-2024 = consommation 2021-2025 / 4 ; rythme de référence = consommation "
        "2011-2021 / 10. L'objectif de -50 % s'apprécie à l'échelle du document d'urbanisme "
        "(SCoT, PLUi) et non commune par commune : la carte sert à repérer les dynamiques, "
        "pas à juger la conformité de chaque commune. Les communes à consommation marginale "
        "ne sont pas classées (pourcentages non significatifs).",
        largeur=52)
    C.cartouche(fig, SRC_CEREMA)
    return fig


def main():
    log("Étape 1 - Consommation d'ENAF")
    d = charger()
    s = serie_annuelle(d)
    t = indicateurs(d)
    com = lire("communes")[["code_insee", "geometry"]]
    gdf = com.merge(t, on="code_insee", how="left")
    assert gdf.conso_1121_ha.notna().all(), "commune sans donnée Cerema"
    ecrire(gdf, "ind_conso_enaf")

    synthese = {
        "conso_1121_ha": t.conso_1121_ha.sum(),
        "conso_2125_ha": t.conso_2125_ha.sum(),
        "moy_an_1121_ha": t.conso_1121_ha.sum() / 10,
        "moy_an_2125_ha": t.conso_2125_ha.sum() / 4,
        "part_hab_1121": t.c1121_hab_ha.sum() / t.conso_1121_ha.sum(),
        "part_act_1121": t.c1121_act_ha.sum() / t.conso_1121_ha.sum(),
    }
    synthese["enveloppe_zan_ha"] = synthese["conso_1121_ha"] * (1 - config.TAUX_REDUCTION)
    synthese["part_enveloppe"] = synthese["conso_2125_ha"] / synthese["enveloppe_zan_ha"]
    synthese["evol_rythme_pct"] = (synthese["moy_an_2125_ha"] / synthese["moy_an_1121_ha"] - 1) * 100
    synthese["projection_2031_ha"] = synthese["conso_2125_ha"] + synthese["moy_an_2125_ha"] * 6

    config.INTERIM.mkdir(exist_ok=True)
    s.to_csv(config.INTERIM / "conso_annuelle_metropole.csv", index=False)
    t.to_csv(config.INTERIM / "indicateurs_conso_communes.csv", index=False)

    dossier_g = config.LIVRABLES / "04_Graphiques"
    dossier_g.mkdir(parents=True, exist_ok=True)
    for nom, fig in (("G01_Consommation_annuelle_ENAF_2011-2024", graphique_annuel(s, synthese)),
                     ("G03_Top15_communes_consommatrices", graphique_top(t))):
        fig.savefig(dossier_g / f"{nom}.png", dpi=200, facecolor="white")
        fig.savefig(dossier_g / f"{nom}.pdf", facecolor="white")
        plt.close(fig)
    fig, annee_dep = graphique_trajectoire(s, synthese)
    synthese["annee_epuisement"] = annee_dep
    fig.savefig(dossier_g / "G02_Trajectoire_ZAN_2021-2031.png", dpi=200, facecolor="white")
    fig.savefig(dossier_g / "G02_Trajectoire_ZAN_2021-2031.pdf", facecolor="white")
    plt.close(fig)

    eau = fond_eau()
    perim = lire("perimetre")
    C.enregistrer(carte_consommation(gdf, synthese, eau, perim), "C01_Consommation_ENAF_2011-2021")
    C.enregistrer(carte_effort(gdf, synthese, eau, perim), "C02_Rythme_consommation_depuis_2021")

    pd.Series(synthese).to_json(config.INTERIM / "synthese_etape1.json", indent=1)
    for k, v in synthese.items():
        log(f"  {k:22s} {v}")
    log("Étape 1 terminée")


if __name__ == "__main__":
    main()
