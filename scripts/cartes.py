"""Charte graphique et gabarits de mise en page des planches cartographiques.

Toutes les planches partagent la même structure : bandeau de titre, carte,
panneau latéral (légende, chiffres clés, commentaire), cartouche
(sources, auteur, date). Les couleurs catégorielles ont été validées pour
les daltonismes (protanopie, deutéranopie) avec un contrôle Delta E OKLab.
"""
import textwrap
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrow, Patch, Rectangle  # noqa: E402

import config  # noqa: E402

# --- Typographie --------------------------------------------------------------
_POLICES = {f.name for f in font_manager.fontManager.ttflist}
POLICE = next((p for p in ("Segoe UI", "Calibri", "Arial") if p in _POLICES), "DejaVu Sans")
plt.rcParams.update({
    "font.family": POLICE,
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": "#52514e",
    "xtick.color": "#898781",
    "ytick.color": "#898781",
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})

# --- Encres et fonds ----------------------------------------------------------
FOND = "#fcfcfb"
ENCRE = "#0b0b0b"
ENCRE_2 = "#52514e"
ENCRE_3 = "#898781"
GRILLE = "#e1e0d9"
AXE = "#c3c2b7"
ACCENT = "#184f95"          # bandeau, filets
EAU = "#cfe0ee"
LIMITE_COM = "#a9a79f"
HORS_TERRITOIRE = "#f1f0ec"

# --- Palettes (validées) -------------------------------------------------------
# Destinations de la consommation d'ENAF - conventions de l'urbanisme
# (habitat rouge-orangé, activités violet, infrastructures gris ; le bleu
# reste réservé à l'eau). Paires adjacentes validées CVD (Delta E >= 16).
# Les deux gris (infrastructures, inconnue) sont neutres par choix et se
# distinguent par la luminosité.
DESTINATIONS = {
    "hab": ("Habitat", "#e5714a"),
    "act": ("Activité économique", "#7b3fa0"),
    "mix": ("Mixte habitat / activité", "#d4a03a"),
    "inf": ("Infrastructures (route, fer)", "#6f6f6f"),
    "inc": ("Destination inconnue", "#c3c2bb"),
}
# Flux d'artificialisation : rouge (artificialisation) / vert (renaturation)
ARTIF = "#b8262b"
DESARTIF = "#159a6b"
# Zonage PLU(i) - convention U rouge / AU orange / A jaune / N vert,
# pas de luminosité ajustés ; codage secondaire (hachures AU + étiquettes).
ZONES = {
    "U": ("Zones urbaines (U)", "#b8262b"),
    "AU": ("Zones à urbaniser (AU)", "#eb6834"),
    "A": ("Zones agricoles (A)", "#d4a800"),
    "N": ("Zones naturelles (N)", "#1f6f3f"),
}
# Classes divergentes « effort de réduction » (bleu = sobriété, rouge = hausse)
DIVERGENT = ["#184f95", "#5598e7", "#eb6834", "#b8262b"]
NEUTRE = "#d9d8d2"
# Rampe séquentielle (magnitude) : bleu 100 -> 700
SEQ_BLEU = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Rampe séquentielle chaude pour la consommation foncière
SEQ_CHAUD = ["#fde7da", "#f8c3a4", "#f19a71", "#e5714a", "#c9502c", "#9f3a1e", "#6e2814"]

def fr(x, nd=0, unite=""):
    """Nombre au format français : espace fine pour les milliers, virgule décimale."""
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",").replace("-", "−")
    return f"{s} {unite}" if unite else s


def pct(x, nd=0, signe=False):
    """Part (0-1) ou pourcentage déjà multiplié -> '56 %'."""
    s = f"{x:+.{nd}f}" if signe else f"{x:.{nd}f}"
    return s.replace(".", ",").replace("-", "−") + " %"


A3_PAYSAGE = (16.54, 11.69)
A4_PAYSAGE = (11.69, 8.27)
A4_PORTRAIT = (8.27, 11.69)


def planche(titre, sous_titre, format_=A3_PAYSAGE, panneau=0.27):
    """Crée une planche : renvoie (fig, ax_carte, ax_panneau)."""
    fig = plt.figure(figsize=format_, facecolor="white")
    l, r = 0.025, 0.975
    haut_bandeau = 0.085 if format_ == A3_PAYSAGE else 0.11
    # bandeau
    fig.add_artist(Rectangle((0, 1 - haut_bandeau), 1, haut_bandeau,
                             transform=fig.transFigure, color=ACCENT, zorder=0))
    fig.text(l, 1 - haut_bandeau * 0.42, titre, color="white", fontsize=20 if format_ == A3_PAYSAGE else 15,
             fontweight="bold", va="center")
    fig.text(l, 1 - haut_bandeau * 0.80, sous_titre, color="#dce8f6",
             fontsize=11 if format_ == A3_PAYSAGE else 9, va="center")
    fig.text(r, 1 - haut_bandeau * 0.42, f"Territoire : {config.EPCI_NOM}", color="white",
             fontsize=12 if format_ == A3_PAYSAGE else 10, ha="right", va="center")
    fig.text(r, 1 - haut_bandeau * 0.80, "Étude indépendante · données ouvertes",
             color="#dce8f6", fontsize=10 if format_ == A3_PAYSAGE else 8, ha="right", va="center")

    bas = 0.06
    h = 1 - haut_bandeau - bas - 0.02
    largeur_carte = (r - l) * (1 - panneau) - 0.01
    ax = fig.add_axes([l, bas, largeur_carte, h])
    ax.set_axis_off()
    axp = fig.add_axes([l + largeur_carte + 0.02, bas, (r - l) - largeur_carte - 0.02, h])
    axp.set_axis_off()
    axp.set_xlim(0, 1)
    axp.set_ylim(0, 1)
    fig.add_artist(Line2D([l + largeur_carte + 0.01] * 2, [bas, bas + h],
                          transform=fig.transFigure, color=GRILLE, lw=0.8))
    return fig, ax, axp


def cartouche(fig, sources, format_=A3_PAYSAGE):
    taille = 8 if format_ == A3_PAYSAGE else 6.5
    fig.add_artist(Line2D([0.025, 0.975], [0.045, 0.045], transform=fig.transFigure,
                          color=GRILLE, lw=0.8))
    fig.text(0.025, 0.025, "Sources : " + sources, fontsize=taille, color=ENCRE_2, va="center")
    fig.text(0.975, 0.025,
             f"Réalisation : {config.AUTEUR} · {date.today().strftime('%m/%Y')} · Lambert-93 (EPSG:2154)",
             fontsize=taille, color=ENCRE_2, ha="right", va="center")


def fond_territoire(ax, communes, eau=None, perimetre=None, etiquettes=None, cadre=None):
    """Fond commun : communes, Seine, contour de la Métropole."""
    if cadre is not None:
        xmin, ymin, xmax, ymax = cadre
    else:
        xmin, ymin, xmax, ymax = communes.total_bounds
        dx, dy = (xmax - xmin) * 0.03, (ymax - ymin) * 0.03
        xmin, xmax, ymin, ymax = xmin - dx, xmax + dx, ymin - dy, ymax + dy
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_facecolor(HORS_TERRITOIRE)
    ax.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, color=HORS_TERRITOIRE, zorder=-10))
    return (xmin, ymin, xmax, ymax)


def surcouches(ax, communes, eau=None, perimetre=None, etiquettes=None, taille_etiq=7.5):
    if eau is not None and not eau.empty:
        eau.plot(ax=ax, color=EAU, edgecolor="none", zorder=5)
    communes.boundary.plot(ax=ax, color="white", linewidth=0.9, zorder=6)
    communes.boundary.plot(ax=ax, color=LIMITE_COM, linewidth=0.35, zorder=7)
    if perimetre is not None:
        perimetre.boundary.plot(ax=ax, color=ENCRE, linewidth=1.3, zorder=8)
    if etiquettes is not None:
        for _, row in etiquettes.iterrows():
            p = row.geometry.representative_point()
            ax.annotate(row["nom"], (p.x, p.y), ha="center", va="center", fontsize=taille_etiq,
                        color=ENCRE, zorder=20,
                        path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])


def echelle_nord(ax, longueur_m=None, position=(0.04, 0.05)):
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    if longueur_m is None:
        brut = (xmax - xmin) / 5
        longueur_m = min((1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000),
                         key=lambda v: abs(v - brut))
    x0 = xmin + (xmax - xmin) * position[0]
    y0 = ymin + (ymax - ymin) * position[1]
    h = (ymax - ymin) * 0.008
    moitie = longueur_m / 2
    ax.add_patch(Rectangle((x0, y0), moitie, h, facecolor=ENCRE, edgecolor=ENCRE, lw=0.6, zorder=30))
    ax.add_patch(Rectangle((x0 + moitie, y0), moitie, h, facecolor="white", edgecolor=ENCRE, lw=0.6, zorder=30))
    def lib(v):
        return (f"{v / 1000:g} km" if longueur_m >= 1000 else f"{v:g} m").replace(".", ",")
    for x, t in ((x0, "0"), (x0 + moitie, lib(moitie).split()[0]), (x0 + longueur_m, lib(longueur_m))):
        ax.text(x, y0 + h * 2.2, t, ha="center", va="bottom", fontsize=7.5, color=ENCRE, zorder=30)
    # flèche du nord
    xn = xmin + (xmax - xmin) * 0.965
    yn = ymin + (ymax - ymin) * 0.90
    L = (ymax - ymin) * 0.05
    ax.add_patch(FancyArrow(xn, yn, 0, L, width=L * 0.08, head_width=L * 0.35, head_length=L * 0.4,
                            length_includes_head=True, color=ENCRE, zorder=30))
    ax.text(xn, yn + L * 1.12, "N", ha="center", va="bottom", fontsize=10, fontweight="bold",
            color=ENCRE, zorder=30)


# --- Panneau latéral ------------------------------------------------------------
class Panneau:
    """Écrit de haut en bas dans l'axe latéral (coordonnées 0-1)."""

    def __init__(self, ax, echelle=1.0):
        self.ax, self.y, self.k = ax, 0.985, echelle

    def titre(self, texte):
        self.y -= 0.012
        self.ax.text(0, self.y, texte.upper(), fontsize=9 * self.k, fontweight="bold", color=ACCENT, va="top")
        self.y -= 0.03 * self.k

    def chiffre(self, valeur, libelle, couleur=ENCRE):
        self.ax.text(0, self.y, valeur, fontsize=21 * self.k, fontweight="bold", color=couleur, va="top")
        self.y -= 0.042 * self.k
        self.ax.text(0, self.y, libelle, fontsize=8.5 * self.k, color=ENCRE_2, va="top", wrap=True)
        self.y -= 0.035 * self.k

    def case(self, couleur, libelle, hachure=None, bord=None, forme="carre"):
        if forme == "trait":
            self.ax.add_line(Line2D([0, 0.06], [self.y - 0.009] * 2, color=couleur, lw=2))
        else:
            self.ax.add_patch(Rectangle((0, self.y - 0.017), 0.06, 0.016, facecolor=couleur,
                                        edgecolor=bord or "white", hatch=hachure, lw=0.6))
        self.ax.text(0.085, self.y - 0.009, libelle, fontsize=8.5 * self.k, color=ENCRE, va="center")
        self.y -= 0.026 * self.k

    def texte(self, texte, taille=8.5, couleur=ENCRE_2, interligne=0.021, largeur=None):
        if largeur:
            texte = "\n".join(textwrap.fill(p, largeur) for p in texte.split("\n"))
        for ligne in texte.split("\n"):
            self.ax.text(0, self.y, ligne, fontsize=taille * self.k, color=couleur, va="top")
            self.y -= interligne * self.k

    def espace(self, h=0.02):
        self.y -= h


def enregistrer(fig, nom, dossier=None, dpi=200):
    dossier = dossier or (config.LIVRABLES / "03_Planches_cartographiques")
    dossier.mkdir(parents=True, exist_ok=True)
    fig.savefig(dossier / f"{nom}.pdf", facecolor="white", dpi=250)  # couches rasterisées à 250 dpi
    fig.savefig(dossier / f"{nom}.png", dpi=dpi, facecolor="white")
    plt.close(fig)
    return dossier / f"{nom}.pdf"


def legende_patches(items):
    return [Patch(facecolor=c, edgecolor="white", label=l) for l, c in items]


