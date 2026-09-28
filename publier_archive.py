"""
=============================================================================
Publication de l'archive : ZIP du jour → releases GitHub
=============================================================================
Objectif :
    Un runner GitHub Actions repart de zéro à chaque exécution : les ZIP qu'il
    télécharge disparaissent avec lui. Ce script publie ceux qui doivent être
    gardés dans une release GitHub par année (archive-2026, archive-2025…).

    Règle, pour chaque ZIP téléchargé aujourd'hui :
      - année en cours : publié le dimanche, soit un ZIP par semaine ;
      - année passée   : publié si son contenu est nouveau. Le fichier d'une
        année finie n'est publié qu'une fois ; en janvier, chaque version de
        l'année N-1 l'est jusqu'à sa finalisation.
    Un contenu déjà publié (même empreinte) ne l'est jamais deux fois : le nom
    de chaque fichier publié se termine par les 12 premiers caractères de son
    empreinte sha256.

Utilisation :
    python publier_archive.py              # applique la règle
    python publier_archive.py --forcer     # publie aussi hors dimanche

Prérequis :
    La commande gh (GitHub CLI), authentifiée : variable GH_TOKEN dans GitHub
    Actions, ou gh auth login en local. ingest.py a été lancé aujourd'hui.
=============================================================================
"""

from contextlib import contextmanager
from datetime import date
from pathlib import Path
import argparse
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

RACINE = Path(__file__).resolve().parent
ARCHIVE = RACINE / "data" / "archive"
LOGS = RACINE / "logs"
DIMANCHE = 6                           # date.weekday() : lundi = 0

log = logging.getLogger("publier_archive")


def configurer_logs() -> None:
    """Écrit les messages à la fois dans le terminal et dans logs/publier_archive.log."""
    LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS / "publier_archive.log", encoding="utf-8"),
        ],
    )


@contextmanager
def etape(nom: str):
    """Annonce le début d'une étape, sa fin et sa durée, ou son échec."""
    log.info("[DÉBUT] %s", nom)
    debut = time.perf_counter()
    try:
        yield
    except Exception:
        log.exception("[ÉCHEC] %s après %.2f s", nom, time.perf_counter() - debut)
        raise
    log.info("[OK]    %s en %.2f s", nom, time.perf_counter() - debut)


def empreinte(fichier: Path) -> str:
    """Calcule l'empreinte sha256 du fichier."""
    h = hashlib.sha256()
    with fichier.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def lancer_gh(*arguments: str, verifier: bool = True) -> subprocess.CompletedProcess:
    """Lance gh sur le dépôt courant (GITHUB_REPOSITORY dans GitHub Actions)."""
    commande = ["gh", *arguments]
    if os.environ.get("GITHUB_REPOSITORY"):
        commande += ["--repo", os.environ["GITHUB_REPOSITORY"]]
    resultat = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8")
    if verifier and resultat.returncode != 0:
        raise RuntimeError(f"{' '.join(commande)} : {resultat.stderr.strip()}")
    return resultat


def lire_publies(tag: str) -> set[str] | None:
    """Noms des fichiers déjà publiés dans la release ; None si elle n'existe pas encore."""
    resultat = lancer_gh("release", "view", tag, "--json", "assets", "--jq", ".assets[].name",
                         verifier=False)
    if resultat.returncode != 0:
        if "not found" in resultat.stderr.lower():
            return None
        raise RuntimeError(f"gh release view {tag} : {resultat.stderr.strip()}")
    return set(resultat.stdout.split())


def decider(annee: int, aujourdhui: date, deja_publie: bool, forcer: bool) -> tuple[bool, str]:
    """Applique la règle de publication ; renvoie (publier ou non, raison)."""
    if deja_publie:
        return False, "contenu déjà publié"
    if annee < aujourdhui.year:
        return True, "année passée, contenu nouveau"
    if forcer:
        return True, "publication forcée"
    if aujourdhui.weekday() == DIMANCHE:
        return True, "année en cours, ZIP de fin de semaine"
    return False, "année en cours, publiée seulement le dimanche"


def publier(chemin_zip: Path, annee: int, sha256_zip: str, publies: set[str] | None) -> None:
    """Crée la release de l'année si besoin, puis y publie le ZIP sous un nom qui porte son empreinte."""
    tag = f"archive-{annee}"
    if publies is None:
        lancer_gh("release", "create", tag, "--title", f"Archive des fichiers annuels {annee}",
                  "--notes", f"ZIP d'origine de https://donnees.roulez-eco.fr/opendata/annee/{annee}, "
                             "tels que téléchargés. Nom : jour de téléchargement, puis début de "
                             "l'empreinte sha256. Publiés par publier_archive.py.")
        log.info("Release %s créée", tag)
    nom = f"{chemin_zip.stem}_{sha256_zip[:12]}.zip"
    with tempfile.TemporaryDirectory() as dossier:
        copie = Path(dossier) / nom
        shutil.copy(chemin_zip, copie)
        lancer_gh("release", "upload", tag, str(copie))
    log.info("Publié : %s dans %s (%.1f Mo)", nom, tag, chemin_zip.stat().st_size / 1e6)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publication des ZIP du jour dans les releases GitHub.")
    parser.add_argument("--forcer", action="store_true",
                        help="publier le ZIP de l'année en cours même si ce n'est pas dimanche")
    args = parser.parse_args()

    configurer_logs()
    log.info("=" * 60)
    log.info("Publication de l'archive des ZIP")
    log.info("=" * 60)
    debut = time.perf_counter()
    aujourdhui = date.today()
    bilan = []

    try:
        with etape("Vérification des prérequis"):
            if shutil.which("gh") is None:
                raise RuntimeError("la commande gh (GitHub CLI) est introuvable")
            zips = sorted(ARCHIVE.glob(f"PrixCarburants_annuel_*_telecharge_{aujourdhui:%Y%m%d}.zip"))
            if not zips:
                raise RuntimeError(f"aucun ZIP téléchargé aujourd'hui dans {ARCHIVE} : lancer ingest.py d'abord")
            log.info("ZIP du jour : %s", ", ".join(z.name for z in zips))

        for chemin_zip in zips:
            annee = int(chemin_zip.name.split("_")[2])
            with etape(f"[{annee}] Publication de {chemin_zip.name}"):
                sha256_zip = empreinte(chemin_zip)
                publies = lire_publies(f"archive-{annee}")
                deja_publie = publies is not None and any(n.endswith(f"_{sha256_zip[:12]}.zip") for n in publies)
                a_publier, raison = decider(annee, aujourdhui, deja_publie, args.forcer)
                if a_publier:
                    publier(chemin_zip, annee, sha256_zip, publies)
                else:
                    log.info("Pas de publication : %s", raison)
                bilan.append((chemin_zip.name, raison))
    except Exception:
        log.error("=" * 60)
        log.error("Publication interrompue après %.2f s, voir le détail ci-dessus", time.perf_counter() - debut)
        log.error("=" * 60)
        return 1

    log.info("=" * 60)
    log.info("Publication terminée")
    for nom, decision in bilan:
        log.info("   - %s : %s", nom, decision)
    log.info("   - Durée totale : %.2f s", time.perf_counter() - debut)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
