"""Étape 5 - Chaîne de traitement complète, rejouable à chaque nouveau millésime.

Usage :
    python scripts/run_all.py              # tout recalculer
    python scripts/run_all.py --depuis 2   # reprendre à partir de l'étape 2

Mise à jour annuelle : quand le Cerema publie un nouveau millésime de la
consommation d'ENAF ou que l'IGN livre un nouveau millésime OCS GE, il suffit
de mettre à jour les URL dans config.py puis de relancer ce script.
"""
import argparse
import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from outils import log  # noqa: E402

ETAPES = [
    ("00_telecharger_donnees", "Collecte et découpage des données sources"),
    ("01_consommation_enaf", "Consommation d'ENAF 2011-2025"),
    ("02_evolution_ocsge", "Occupation du sol et artificialisation 2019-2022"),
    ("03_plui_occupation", "Croisement PLUi x occupation du sol"),
    ("04_gisements_densification", "Gisements de densification"),
    ("05_livrables", "Exports SIG, tableur, atlas communal, carte web"),
    ("06_documents", "Note méthodologique, fiche tutoriel, bordereau"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depuis", type=int, default=0, help="numéro de la première étape à exécuter")
    args = parser.parse_args()
    debut = time.time()
    log(f"Diagnostic foncier ZAN - {config.EPCI_NOM} (SIREN {config.EPCI_SIREN})")
    for i, (module, libelle) in enumerate(ETAPES):
        if i < args.depuis:
            continue
        log(f"=== Étape {i} : {libelle}")
        t = time.time()
        importlib.import_module(module).main()
        log(f"=== Étape {i} terminée en {time.time() - t:.0f} s")
    log(f"Chaîne complète exécutée en {(time.time() - debut) / 60:.1f} min")


if __name__ == "__main__":
    main()
