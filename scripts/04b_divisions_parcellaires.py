"""Étape 4 bis - Divisions parcellaires observées 2018-2026.

Les déclarations préalables de division ne sont pas publiées en données ouvertes.
On repère donc les divisions effectivement réalisées en comparant deux millésimes du
cadastre Etalab :
  - une parcelle de 2018 qui a disparu en 2026 et dont la surface est couverte à
    au moins 90 % par 2 nouvelles parcelles ou plus a été divisée ;
  - l'année de division est la date de création des nouvelles parcelles ;
  - les sections remaniées (plus de 50 % des numéros changés) sont exclues, pour ne pas
    prendre une renumérotation pour une division.

Chaque division est qualifiée par la zone du PLUi et par l'état du sol en 2019 (OCS GE) :
une parcelle déjà artificialisée (jardin, cour, bâti) se densifie sans consommer d'ENAF.
Calibration : taux de division observé des grandes parcelles en zone U habitat, comparé
à l'hypothèse de mobilisation retenue à l'étape 4.

Livrables : planche C09, graphique G06 et un atlas dédié (07_Atlas_divisions).
"""
import importlib
import json
import shutil
import subprocess

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, Ellipse, Rectangle

import cartes as C
import config
from outils import SESSION, ecrire, fond_eau, lire, log

T0, T1 = config.CADASTRE_MILLESIMES
A0, A1 = int(T0[:4]), int(T1[:4])
DOSSIER_ATLAS = config.LIVRABLES / "07_Atlas_divisions"
PREFIXES_HABITAT = ("UA", "UB", "UC", "UD", "UR")
CATEGORIES = {  # zone du PLUi de la parcelle mère
    "U habitat": ("Zone U à dominante habitat", "#e5714a"),
    "U autre": ("Autre zone U (activités, équipements)", "#7b3fa0"),
    "AU": ("Zone à urbaniser (AU)", "#d4a03a"),
    "A ou N": ("Zone agricole ou naturelle", "#1f6f3f"),
}
COUL_DIV = "#f0a04b"  # même teinte que les « divisions parcellaires » de l'étape 4


def telecharger_cadastre(insee, millesime):
    dossier = config.RAW / "cadastre" / millesime
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"cadastre-{insee}-parcelles.json.gz"
    if not f.exists():
        url = (f"{config.CADASTRE_ETALAB}/{millesime}/geojson/communes/"
               f"{config.DEPARTEMENT}/{insee}/cadastre-{insee}-parcelles.json.gz")
        part = f.with_suffix(".part")
        if shutil.which("curl"):  # curl (inclus dans Windows 10+) : plus robuste derrière certains réseaux
            subprocess.run(["curl", "-sSfL", "--retry", "3", "-o", str(part), url], check=True, timeout=300)
        else:
            with SESSION.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(part, "wb") as out:
                    shutil.copyfileobj(r.raw, out)  # gzip conservé tel quel, lu via /vsigzip/
        part.rename(f)
    gdf = gpd.read_file(f"/vsigzip/{f.as_posix()}", engine="pyogrio").to_crs(config.CRS)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf


def detecter(insee, nom):
    a, b = telecharger_cadastre(insee, T0), telecharger_cadastre(insee, T1)
    disparues = a[~a.id.isin(b.id)].copy()
    nouvelles = b[~b.id.isin(a.id)].copy()
    # sections remaniées : la majorité des numéros a changé
    part = disparues.groupby("section").size() / a.groupby("section").size()
    remaniees = set(part[part > config.SEUIL_REMANIEMENT].index)
    disparues = disparues[~disparues.section.isin(remaniees)]
    if disparues.empty or nouvelles.empty:
        return None, None, len(remaniees)
    # rattachement de chaque nouvelle parcelle à la parcelle mère qui la contient
    pts = nouvelles.copy()
    pts["geometry"] = nouvelles.geometry.representative_point()
    lien = gpd.sjoin(pts[["id", "geometry"]], disparues[["id", "geometry"]].rename(columns={"id": "id_mere"}),
                     predicate="within", how="inner")
    enfants = nouvelles.merge(lien[["id", "id_mere"]], on="id")
    enfants["surface_m2"] = enfants.area
    agg = enfants.groupby("id_mere").agg(nb_lots=("id", "size"), surface_lots=("surface_m2", "sum"),
                                         date=("created", "min"))
    meres = disparues.rename(columns={"id": "id_mere"}).merge(agg, left_on="id_mere", right_index=True)
    meres["surface_m2"] = meres.area
    meres = meres[(meres.nb_lots >= 2) & (meres.surface_lots >= config.COUVERTURE_MIN_DIVISION * meres.surface_m2)]
    meres["annee"] = pd.to_datetime(meres.date, errors="coerce").dt.year
    meres["code_insee"], meres["commune"] = insee, nom
    meres["lots_crees"] = meres.nb_lots - 1
    enfants = enfants[enfants.id_mere.isin(meres.id_mere)]
    enfants["annee"] = pd.to_datetime(enfants.created, errors="coerce").dt.year
    enfants["code_insee"] = insee
    return (meres[["code_insee", "commune", "id_mere", "section", "surface_m2", "nb_lots", "lots_crees",
                   "annee", "geometry"]],
            enfants[["code_insee", "id", "id_mere", "surface_m2", "annee", "geometry"]], len(remaniees))


def qualifier(meres, zones, ocs19):
    """Zone du PLUi majoritaire et part artificialisée en 2019 de chaque parcelle mère."""
    z = zones.copy()
    lib = z.libelle.fillna("")
    z["categorie"] = np.select(
        [(z.famille == "U") & lib.str.startswith(PREFIXES_HABITAT) & ~lib.str.startswith("URX"),
         z.famille == "U", z.famille == "AU"],
        ["U habitat", "U autre", "AU"], default="A ou N")
    x = gpd.overlay(meres[["id_mere", "geometry"]], z[["categorie", "libelle", "geometry"]],
                    how="intersection", keep_geom_type=True)
    x["a"] = x.area
    maj = x.sort_values("a").groupby("id_mere").last()
    meres["categorie"] = meres.id_mere.map(maj.categorie).fillna("A ou N")
    meres["zone_plui"] = meres.id_mere.map(maj.libelle)
    o = gpd.overlay(meres[["id_mere", "geometry"]], ocs19[ocs19.artif][["geometry"]],
                    how="intersection", keep_geom_type=True)
    meres["part_artif_2019"] = (meres.id_mere.map(o.area.groupby(o.id_mere).sum()).fillna(0)
                                / meres.area).clip(0, 1).round(3)
    meres["etat_sol_2019"] = np.where(meres.part_artif_2019 >= 0.5, "Déjà artificialisée (jardin, cour, bâti)",
                                      "Naturelle, agricole ou forestière")
    return meres


def calibration(meres, insee_list, zones):
    """Taux de division observé des parcelles ≥ seuil en zone U habitat (communes test)."""
    res = {}
    zu = zones[(zones.famille == "U") & zones.libelle.fillna("").str.startswith(PREFIXES_HABITAT)
               & ~zones.libelle.fillna("").str.startswith("URX")]
    for insee in insee_list:
        a = telecharger_cadastre(insee, T0)
        pts = a.copy()
        pts["geometry"] = a.geometry.representative_point()
        dans_u = gpd.sjoin(pts[["id", "geometry"]], zu[zu.code_insee == insee][["geometry"]],
                           predicate="within", how="inner").id.unique()
        grandes = a[a.id.isin(dans_u) & (a.area >= config.SURFACE_MIN_DIVISION_M2)]
        divisees = meres[(meres.code_insee == insee) & meres.id_mere.isin(grandes.id)]
        duree = (pd.Timestamp(T1) - pd.Timestamp(T0)).days / 365.25
        taux = len(divisees) / max(len(grandes), 1)
        res[config.COMMUNES_DENSIFICATION[insee]] = {
            "parcelles_candidates_2018": int(len(grandes)), "divisees": int(len(divisees)),
            "taux_periode_pct": round(taux * 100, 1), "taux_10_ans_pct": round(taux / duree * 10 * 100, 1)}
    return res


# --- Graphique et planche -------------------------------------------------------------
def graphique_annuel(meres):
    t = meres.dropna(subset=["annee"]).pivot_table(index="annee", columns="categorie", values="id_mere",
                                                   aggfunc="count", fill_value=0)
    t = t.reindex(range(A0, A1 + 1), fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 5.6))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.12)
    bas = np.zeros(len(t))
    for cat, (lib, coul) in CATEGORIES.items():
        v = t[cat].to_numpy() if cat in t else np.zeros(len(t))
        ax.bar(t.index, v, bottom=bas, width=0.62, color=coul, edgecolor="white", lw=1.2, label=lib)
        bas += v
    for x, y in zip(t.index, bas):
        ax.text(x, y + bas.max() * 0.01, f"{int(y)}", ha="center", va="bottom", fontsize=8.5, color=C.ENCRE_2)
    ax.text(A1, bas[-1] + bas.max() * 0.07, "janv.-sept.", ha="center", fontsize=8, color=C.ENCRE_3)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C.AXE)
    ax.yaxis.grid(True, color=C.GRILLE, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_xticks(list(t.index))
    ax.set_ylabel("Parcelles divisées", color=C.ENCRE_2)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=4, frameon=False, fontsize=8.5,
              handlelength=1.2, columnspacing=1.6)
    fig.suptitle(f"Divisions parcellaires par année, {A0}-{A1}", x=0.07, ha="left", fontsize=14,
                 fontweight="bold", color=C.ENCRE, y=0.965)
    fig.text(0.07, 0.885, f"{config.EPCI_NOM} : parcelles divisées selon la zone du PLUi "
             "(année de création des nouvelles parcelles)", fontsize=9.5, color=C.ENCRE_2)
    fig.text(0.07, 0.03, f"Source : DGFiP, cadastre Etalab ({T0} et {T1}) ; Géoportail de l'Urbanisme. "
             f"Réalisation : {config.AUTEUR}.", fontsize=7.5, color=C.ENCRE_3)
    return fig


def planche(ind, com, perim, eau, synth):
    fig, ax, axp = C.planche(f"Divisions parcellaires {A0}-{A1}",
                             "Parcelles divisées repérées par comparaison des millésimes du cadastre")
    C.fond_territoire(ax, com)
    com.plot(ax=ax, color="#f6f5f1", edgecolor="none", zorder=1)
    C.surcouches(ax, com, eau, perim)
    g = com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee")
    vmax, rmax = max(g.div_nb.max(), 1), 2000
    pts = g[g.div_nb > 0].sort_values("div_nb", ascending=False)
    for _, r in pts.iterrows():
        p = r.geometry.representative_point()
        ax.add_patch(Circle((p.x, p.y), rmax * np.sqrt(r.div_nb / vmax), facecolor=COUL_DIV, alpha=0.9,
                            edgecolor="white", lw=1, zorder=10))
    for _, r in g.nlargest(8, "div_nb").iterrows():
        p = r.geometry.representative_point()
        ax.annotate(f"{r.nom}\n{int(r.div_nb)}", (p.x, p.y), ha="center", va="center", fontsize=7.5,
                    color=C.ENCRE, fontweight="semibold", zorder=20,
                    path_effects=[C.pe.withStroke(linewidth=2.6, foreground="white")])
    C.echelle_nord(ax)
    P = C.Panneau(axp)
    P.titre("Chiffres clés")
    P.chiffre(C.fr(synth["nb_divisions"], 0), f"parcelles divisées entre {A0} et {A1}, "
              f"créant {C.fr(synth['lots_crees'], 0)} lots supplémentaires")
    P.chiffre(C.pct(synth["part_u_habitat"] * 100), "des divisions en zone U à dominante habitat")
    P.chiffre(C.pct(synth["part_div_deja_artif"] * 100),
              f"des divisions sur des terrains déjà artificialisés en 2019 "
              f"({C.pct(synth['part_u_hab_deja_artif'] * 100)} en zone U habitat) : "
              "densification sans consommation d'ENAF")
    P.espace(0.01)
    P.titre("Légende")
    P.texte("Parcelles divisées (nombre)", taille=8.5, couleur=C.ENCRE)
    x0, x1 = ax.get_xlim()
    pc, pp = ax.get_position(), axp.get_position()
    ech = (pc.width / (x1 - x0)) / pp.width
    ratio = (pp.height * C.A3_PAYSAGE[1]) / (pp.width * C.A3_PAYSAGE[0])
    vals = [v for v in (400, 200, 50) if v <= vmax * 1.05] or [int(vmax)]
    rleg = rmax * np.sqrt(vals[0] / vmax) * ech
    cx, base = 0.02 + rleg, P.y - 2 * rleg / ratio - 0.005
    for v in vals:
        r = rmax * np.sqrt(v / vmax) * ech
        axp.add_patch(Ellipse((cx, base + r / ratio), 2 * r, 2 * r / ratio, facecolor="none",
                              edgecolor=C.ENCRE_2, lw=0.8))
        axp.plot([cx, cx + rleg + 0.04], [base + 2 * r / ratio] * 2, color=C.ENCRE_3, lw=0.5)
        axp.text(cx + rleg + 0.05, base + 2 * r / ratio, str(v), va="center", fontsize=8, color=C.ENCRE)
    P.y = base - 0.03
    P.case(C.EAU, "Seine et plans d'eau")
    P.espace(0.01)
    P.titre("Méthode")
    P.texte(f"Une parcelle de {A0} disparue en {A1} et couverte à 90 % ou plus par au moins deux nouvelles "
            "parcelles est comptée comme divisée. Les sections remaniées sont exclues. Les déclarations "
            "préalables de division ne sont pas en open data : ce sont ici les divisions inscrites au "
            "cadastre, pas les autorisations déposées.", largeur=52)
    C.cartouche(fig, f"DGFiP, cadastre Etalab ({T0}, {T1}) ; IGN, OCS GE 2019, ADMIN EXPRESS ; "
                     "Géoportail de l'Urbanisme (PLUi 04/05/2026)")
    return fig


# --- Atlas dédié ----------------------------------------------------------------------
def page_couverture(pdf, synth, n_pages):
    fig = plt.figure(figsize=C.A4_PAYSAGE)
    fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.07, 0.70, "Atlas des divisions parcellaires", color="white", fontsize=34, fontweight="bold")
    fig.text(0.07, 0.62, f"Densification du tissu existant, {A0}-{A1}", color="#dce8f6", fontsize=18)
    fig.text(0.07, 0.56, f"{config.EPCI_NOM} · {n_pages} communes ayant au moins "
             f"{config.SEUIL_ATLAS_DIVISIONS} divisions", color="white", fontsize=13)
    fig.text(0.07, 0.52, "Étude indépendante réalisée à partir de données ouvertes - document non officiel",
             color="#dce8f6", fontsize=10)
    fig.text(0.07, 0.40, f"{C.fr(synth['nb_divisions'], 0)} parcelles divisées · "
             f"{C.fr(synth['lots_crees'], 0)} lots créés · {C.pct(synth['part_div_deja_artif'] * 100)} "
             "des divisions sur des terrains déjà artificialisés", color="white", fontsize=12)
    fig.text(0.07, 0.07, f"Réalisation : {config.AUTEUR}", color="#dce8f6", fontsize=10)
    fig.text(0.07, 0.04, f"Sources : DGFiP, cadastre Etalab ({T0}, {T1}) ; IGN, OCS GE 2019 ; "
             "Géoportail de l'Urbanisme", color="#dce8f6", fontsize=8.5)
    pdf.savefig(fig)
    plt.close(fig)


def page_synthese(pdf, ind):
    fig = plt.figure(figsize=C.A4_PAYSAGE, facecolor="white")
    fig.add_artist(Rectangle((0, 0.915), 1, 0.085, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.03, 0.958, "Tableau de synthèse par commune", color="white", fontsize=17,
             fontweight="bold", va="center")
    t = ind[ind.div_nb > 0].sort_values("div_nb", ascending=False).head(40)
    cols = [("Commune", "nom", 0.03), ("Divisions", "div_nb", 0.40), ("Lots", "div_lots", 0.53),
            ("Zone U hab.", "div_u_hab", 0.63), ("Déjà artif.", "part_artif_pct", 0.77),
            ("/100 ha U", "div_100ha_u", 0.90)]
    for j, demi in enumerate((t.iloc[:20], t.iloc[20:])):
        if demi.empty:
            continue
        dx = 0 if j == 0 else 0.48
        echelle = 0.48 / 0.97
        y = 0.87
        for lib, _, x in cols:
            fig.text(dx + x * echelle + 0.01, y, lib, fontsize=7, fontweight="bold", color=C.ACCENT)
        for _, r in demi.iterrows():
            y -= 0.038
            for lib, col, x in cols:
                v = r[col]
                txt = r.nom if col == "nom" else (C.pct(v) if col == "part_artif_pct" else
                                                  C.fr(v, 1 if col == "div_100ha_u" else 0))
                fig.text(dx + x * echelle + 0.01, y, txt, fontsize=7.5, color=C.ENCRE)
            fig.add_artist(plt.Line2D([dx + 0.01, dx + 0.47], [y - 0.012] * 2, transform=fig.transFigure,
                                      color=C.GRILLE, lw=0.4))
    fig.text(0.03, 0.04, "Communes classées par nombre de divisions (40 premières). Zone U hab. : divisions en "
             "zone U à dominante habitat. Déjà artif. : part des divisions portant sur un terrain déjà artificialisé "
             "en 2019 (OCS GE). /100 ha U : divisions pour 100 ha de zone U.", fontsize=7, color=C.ENCRE_3)
    pdf.savefig(fig)
    plt.close(fig)


def page_commune(pdf, r, meres_c, enfants_c, com, zones, eau, num, total):
    fig = plt.figure(figsize=C.A4_PAYSAGE, facecolor="white")
    fig.add_artist(Rectangle((0, 0.915), 1, 0.085, transform=fig.transFigure, color=C.ACCENT))
    fig.text(0.03, 0.958, r.nom, color="white", fontsize=17, fontweight="bold", va="center")
    fig.text(0.97, 0.958, f"Divisions parcellaires {A0}-{A1} · INSEE {r.code_insee}", color="#dce8f6",
             fontsize=9.5, ha="right", va="center")
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
    if eau is not None:
        gpd.clip(eau, geom.buffer(3000)).plot(ax=ax, color=C.EAU, edgecolor="none", zorder=3)
    for cat, (lib, coul) in CATEGORIES.items():
        sel = meres_c[meres_c.categorie == cat]
        if not sel.empty:
            sel.plot(ax=ax, color=coul, edgecolor=coul, lw=0.6, alpha=0.85, zorder=5)
    if not enfants_c.empty:
        enfants_c.boundary.plot(ax=ax, color="#1f1f1f", lw=0.35, zorder=6)
    com.boundary.plot(ax=ax, color="white", lw=1.2, zorder=4)
    geom.boundary.plot(ax=ax, color=C.ENCRE, lw=1.3, zorder=8)
    C.echelle_nord(ax)
    # panneau
    def ligne(y, lib, val, gras=False):
        fig.text(0.65, y, lib, fontsize=8.5, color=C.ENCRE_2, va="center")
        fig.text(0.97, y, val, fontsize=9 if gras else 8.5, color=C.ENCRE, ha="right", va="center",
                 fontweight="bold" if gras else "normal")
        fig.add_artist(plt.Line2D([0.65, 0.97], [y - 0.014] * 2, transform=fig.transFigure, color=C.GRILLE, lw=0.5))
    fig.text(0.65, 0.885, "DIVISIONS INSCRITES AU CADASTRE", fontsize=8.5, fontweight="bold", color=C.ACCENT)
    y = 0.85
    for lib, val, gras in (("Parcelles divisées", C.fr(r.div_nb, 0), True),
                           ("Lots créés", C.fr(r.div_lots, 0), True),
                           ("Dont en zone U à dominante habitat", C.fr(r.div_u_hab, 0), False),
                           ("Divisions sur terrain déjà artificialisé (2019)", C.pct(r.part_artif_pct), False),
                           ("Divisions pour 100 ha de zone U", C.fr(r.div_100ha_u, 1), False)):
        ligne(y, lib, val, gras)
        y -= 0.034
    # barres annuelles
    axb = fig.add_axes([0.67, 0.36, 0.30, 0.22])
    an = meres_c.dropna(subset=["annee"]).groupby("annee").size().reindex(range(A0, A1 + 1), fill_value=0)
    axb.bar(an.index, an.values, color=COUL_DIV, width=0.65, edgecolor="white")
    for s in ("top", "right", "left"):
        axb.spines[s].set_visible(False)
    axb.spines["bottom"].set_color(C.AXE)
    axb.yaxis.grid(True, color=C.GRILLE, lw=0.5)
    axb.set_axisbelow(True)
    axb.tick_params(labelsize=7, length=0)
    axb.set_xticks(list(range(A0, A1 + 1, 2)))
    axb.set_title("Divisions par année", fontsize=8.5, loc="left", color=C.ENCRE)
    # légende
    y = 0.28
    for cat, (lib, coul) in CATEGORIES.items():
        fig.add_artist(Rectangle((0.65, y), 0.014, 0.016, transform=fig.transFigure, color=coul, alpha=0.85))
        fig.text(0.67, y + 0.008, f"Parcelle divisée : {lib}", fontsize=7, color=C.ENCRE, va="center")
        y -= 0.025
    fig.add_artist(plt.Line2D([0.65, 0.664], [y + 0.008] * 2, transform=fig.transFigure, color="#1f1f1f", lw=0.8))
    fig.text(0.67, y + 0.008, "Limites des nouvelles parcelles", fontsize=7, color=C.ENCRE, va="center")
    fig.add_artist(Rectangle((0.65, y - 0.025), 0.014, 0.016, transform=fig.transFigure, color="#ece6dc"))
    fig.text(0.67, y - 0.017, "Zone urbaine (U) du PLUi", fontsize=7, color=C.ENCRE, va="center")
    fig.text(0.03, 0.025, f"Sources : DGFiP, cadastre Etalab ({T0}, {T1}) ; IGN OCS GE 2019, ADMIN EXPRESS ; "
             "Géoportail de l'Urbanisme (PLUi 04/05/2026).", fontsize=6.5, color=C.ENCRE_3)
    fig.text(0.97, 0.025, f"{config.AUTEUR} · page {num}/{total}", fontsize=6.5, color=C.ENCRE_3, ha="right")
    pdf.savefig(fig, dpi=200)
    plt.close(fig)


def atlas(meres, enfants, ind, com, zones, eau, synth):
    DOSSIER_ATLAS.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_ATLAS / "Atlas_divisions_parcellaires_Metropole_Rouen.pdf"
    sel = com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee")
    sel = sel[sel.div_nb >= config.SEUIL_ATLAS_DIVISIONS].sort_values("nom")
    total = len(sel) + 2
    with PdfPages(chemin) as pdf:
        page_couverture(pdf, synth, len(sel))
        page_synthese(pdf, ind.merge(com[["code_insee", "nom"]], on="code_insee"))
        for i, (_, r) in enumerate(sel.iterrows(), start=3):
            page_commune(pdf, r, meres[meres.code_insee == r.code_insee],
                         enfants[enfants.code_insee == r.code_insee], com, zones, eau, i, total)
        meta = pdf.infodict()
        meta["Title"] = f"Atlas des divisions parcellaires {A0}-{A1} - {config.EPCI_NOM}"
        meta["Author"] = config.AUTEUR
    log(f"  atlas des divisions : {chemin.name} ({total} pages)")


def main():
    log(f"Étape 4 bis - Divisions parcellaires {T0} -> {T1}")
    com = lire("communes")
    zones = lire("plui_zonage_qualifie")
    perim, eau = lire("perimetre"), fond_eau()
    toutes_meres, tous_enfants, remaniements = [], [], 0
    for _, c in com.iterrows():
        m, e, nr = detecter(c.code_insee, c.nom)
        remaniements += nr
        if m is not None and len(m):
            toutes_meres.append(m)
            tous_enfants.append(e)
    meres = gpd.GeoDataFrame(pd.concat(toutes_meres, ignore_index=True), crs=config.CRS)
    enfants = gpd.GeoDataFrame(pd.concat(tous_enfants, ignore_index=True), crs=config.CRS)
    log(f"  {len(meres)} divisions, {remaniements} sections remaniées exclues")
    ocs19 = lire("ocsge_2019_occupation_sol")
    ocs19["artif"] = importlib.import_module("02_evolution_ocsge").est_artificialise(ocs19.code_cs, ocs19.code_us)
    meres = qualifier(meres, zones, ocs19)
    ecrire(meres, "divisions_parcellaires")
    ecrire(enfants, "lots_issus_divisions")

    # indicateurs communaux
    zu = zones[zones.famille == "U"]
    zone_u = zu.area.groupby(zu.code_insee).sum() / 1e4
    g = meres.groupby("code_insee")
    ind = pd.DataFrame({"code_insee": com.code_insee})
    ind["div_nb"] = ind.code_insee.map(g.size()).fillna(0).astype(int)
    ind["div_lots"] = ind.code_insee.map(g.lots_crees.sum()).fillna(0).astype(int)
    ind["div_u_hab"] = ind.code_insee.map(meres[meres.categorie == "U habitat"].groupby("code_insee").size()
                                          ).fillna(0).astype(int)
    deja = (meres.part_artif_2019 >= 0.5).groupby(meres.code_insee).mean()
    ind["part_artif_pct"] = (ind.code_insee.map(deja) * 100).fillna(0).round(1)
    ind["div_100ha_u"] = (ind.div_nb / ind.code_insee.map(zone_u) * 100).fillna(0).round(2)
    ecrire(com[["code_insee", "nom", "geometry"]].merge(ind, on="code_insee"), "ind_divisions")

    synth = {
        "periode": f"{T0} -> {T1}",
        "nb_divisions": int(len(meres)), "lots_crees": int(meres.lots_crees.sum()),
        "surface_divisee_ha": float(meres.surface_m2.sum() / 1e4),
        "part_u_habitat": float((meres.categorie == "U habitat").mean()),
        "part_deja_artif": float((meres.surface_m2 * meres.part_artif_2019).sum() / meres.surface_m2.sum()),
        # part en nombre : les grandes parcelles agricoles divisées pèsent trop dans la part en surface
        "part_div_deja_artif": float((meres.part_artif_2019 >= 0.5).mean()),
        "part_u_hab_deja_artif": float((meres[meres.categorie == "U habitat"].part_artif_2019 >= 0.5).mean()),
        "surface_mediane_u_hab_m2": float(meres[meres.categorie == "U habitat"].surface_m2.median()),
        "sections_remaniees_exclues": int(remaniements),
        "par_categorie": meres.categorie.value_counts().to_dict(),
        "calibration": calibration(meres, list(config.COMMUNES_DENSIFICATION), zones),
        "hypothese_mobilisation_10_ans_pct": config.TAUX_MOBILISATION["Division parcellaire"] * 100,
    }
    (config.INTERIM / "synthese_etape4b.json").write_text(json.dumps(synth, indent=1, ensure_ascii=False),
                                                          encoding="utf-8")
    G = config.LIVRABLES / "04_Graphiques"
    fig = graphique_annuel(meres)
    fig.savefig(G / "G06_Divisions_parcellaires_par_annee.png", dpi=200, facecolor="white")
    fig.savefig(G / "G06_Divisions_parcellaires_par_annee.pdf", facecolor="white")
    plt.close(fig)
    C.enregistrer(planche(ind, com, perim, eau, synth), "C09_Divisions_parcellaires_2018-2026")
    atlas(meres, enfants, ind, com, zones, eau, synth)
    for k in ("nb_divisions", "lots_crees", "surface_divisee_ha", "part_u_habitat", "part_div_deja_artif",
              "sections_remaniees_exclues"):
        log(f"  {k:28s} {synth[k]}")
    log(f"  calibration : {synth['calibration']}")
    log("Étape 4 bis terminée")


if __name__ == "__main__":
    main()
