"""
=============================================================================
Ingestion : fichiers annuels des prix des carburants → Parquet (couche raw)
=============================================================================
Objectif :
    Télécharge le fichier annuel de donnees.roulez-eco.fr (ZIP contenant un
    XML), l'archive tel quel, le lit en flux et écrit deux fichiers Parquet
    par année :
      - prix     : une ligne par relevé de prix (balise <prix>) ;
      - stations : une ligne par point de vente (balise <pdv>), avec son
                   adresse et sa ville.
    Les vues DuckDB raw.prix et raw.stations donnent accès à tous les Parquet.

    Le même script sert à la reprise de l'historique et à l'exécution
    quotidienne : le fichier de l'année en cours contient tous les relevés
    depuis le 1er janvier, il est donc retéléchargé et réécrit en entier.

Utilisation :
    python ingest.py                 # exécution quotidienne
    python ingest.py 2025 2026       # années imposées
    python ingest.py --forcer        # retélécharge même si le ZIP du jour existe

    Sans année, le script traite :
      - l'année en cours ;
      - l'année précédente pendant les 15 premiers jours de janvier : son
        fichier n'est finalisé que quelques jours après le 1er janvier ;
      - toute année depuis PREMIERE_ANNEE dont les Parquet manquent : sur une
        machine neuve (runner GitHub Actions), l'historique est reconstruit.

    Après le chargement, l'archive des ZIP est nettoyée : pour chaque année,
    le dernier ZIP de chaque semaine est gardé, sans doublon de contenu.

Attention :
    Les fichiers Parquet d'une année sont entièrement remplacés à chaque exécution.
    La base data/carburant.duckdb ne doit pas être ouverte par un autre programme.
=============================================================================
"""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import argparse
import hashlib
import logging
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

URL_ANNEE = "https://donnees.roulez-eco.fr/opendata/annee/{annee}"
RACINE = Path(__file__).resolve().parent
ARCHIVE = RACINE / "data" / "archive"
RAW = RACINE / "data" / "raw"        # un sous-dossier par entité : prix/, stations/
DB = RACINE / "data" / "carburant.duckdb"
LOGS = RACINE / "logs"

TAILLE_LOT = 500_000                 # lignes écrites d'un coup dans un Parquet
PREMIERE_ANNEE = 2025                # profondeur de l'historique chargé
JOURS_ANNEE_PRECEDENTE = 15          # en janvier, recharger aussi l'année N-1
RETARD_MAX_JOURS = 2                 # au-delà, le fichier de l'année en cours est suspect

# Colonnes de la couche raw. Les attributs et les textes du XML sont gardés en
# texte, sous leur nom d'origine ; seuls les `id` et `nom` de <pdv> et <prix>,
# qui portent le même nom, sont préfixés par leur balise. Le typage se fait dans dbt.
COLONNES = {
    "prix": ["pdv_id", "latitude", "longitude", "cp", "pop",
             "prix_id", "prix_nom", "maj", "valeur"],
    "stations": ["pdv_id", "latitude", "longitude", "cp", "pop", "adresse", "ville"],
}
COLONNES_TECHNIQUES = [
    ("_source_year", pa.int16()),
    ("_source_file", pa.string()),
    ("_source_sha256", pa.string()),
    ("_loaded_at", pa.timestamp("us", tz="UTC")),
]
SCHEMAS = {
    entite: pa.schema([(nom, pa.string()) for nom in colonnes] + COLONNES_TECHNIQUES)
    for entite, colonnes in COLONNES.items()
}

log = logging.getLogger("ingest")


class SourceError(ValueError):
    """Le fichier reçu n'a pas la forme attendue (pas un ZIP, pas le bon XML…)."""


def configurer_logs() -> None:
    """Écrit les messages à la fois dans le terminal et dans logs/ingest.log."""
    LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS / "ingest.log", encoding="utf-8"),
        ],
    )


def formater(nombre: int) -> str:
    """Formate un entier à la française : 4172763 -> '4 172 763'."""
    return f"{nombre:,}".replace(",", " ")


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


def choisir_annees(aujourdhui: date) -> dict[int, str]:
    """Années à charger quand aucune n'est imposée, avec la raison de chacune."""
    annees = {aujourdhui.year: "année en cours"}
    if aujourdhui.timetuple().tm_yday <= JOURS_ANNEE_PRECEDENTE:
        annees[aujourdhui.year - 1] = "année précédente, peut-être pas encore finalisée"
    for annee in range(PREMIERE_ANNEE, aujourdhui.year):
        parquets = [RAW / entite / f"annee={annee}" / f"{entite}_{annee}.parquet" for entite in COLONNES]
        if annee not in annees and not all(p.is_file() for p in parquets):
            annees[annee] = "Parquet absents"
    return dict(sorted(annees.items()))


def telecharger(annee: int, forcer: bool = False) -> Path:
    """Télécharge le ZIP de l'année et l'archive sous un nom daté du jour.

    Le ZIP du jour est réutilisé s'il existe déjà : relancer le script dans
    la journée ne retélécharge rien, sauf si forcer est vrai.
    """
    dest = ARCHIVE / f"PrixCarburants_annuel_{annee}_telecharge_{date.today():%Y%m%d}.zip"
    if dest.is_file() and not forcer:
        log.info("ZIP du jour déjà archivé, pas de téléchargement : %s", dest.name)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    url = URL_ANNEE.format(annee=annee)

    log.info("Téléchargement de %s", url)
    try:
        with urllib.request.urlopen(url, timeout=120) as reponse:
            # Le code HTTP ne suffit pas : pour une date indisponible, le serveur
            # répond 200 avec une page HTML. Seul le Content-Type fait foi.
            type_contenu = reponse.headers.get_content_type()
            if type_contenu != "application/zip":
                raise SourceError(f"Content-Type {type_contenu!r} au lieu de 'application/zip'")
            with tmp.open("wb") as sortie:
                while bloc := reponse.read(1024 * 1024):
                    sortie.write(bloc)
        if not zipfile.is_zipfile(tmp):
            raise SourceError("le fichier reçu n'est pas un ZIP valide")
    except Exception:
        tmp.unlink(missing_ok=True)  # sinon le prochain essai partirait d'un fichier tronqué
        raise

    tmp.replace(dest)  # renommage atomique : jamais de fichier incomplet sous le nom final
    log.info("ZIP archivé : %s (%.1f Mo)", dest.name, dest.stat().st_size / 1e6)
    return dest


def empreinte(fichier: Path) -> str:
    """Calcule l'empreinte sha256 du fichier, pour savoir quelle version a été chargée."""
    h = hashlib.sha256()
    with fichier.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):  # par blocs de 1 Mo, pour ne pas tout charger en mémoire
            h.update(bloc)
    return h.hexdigest()


def lire_pdv(chemin_zip: Path, compteurs: dict):
    """Renvoie, pour chaque <pdv>, la ligne de la station et la liste de ses relevés.

    Les tuples suivent l'ordre de COLONNES["stations"] et COLONNES["prix"].
    Le XML est lu directement dans le ZIP, un <pdv> à la fois. On passe des
    octets au parseur : il suit la déclaration d'encodage du fichier
    (ISO-8859-1), alors qu'une lecture en texte UTF-8 casserait les accents.
    """
    with zipfile.ZipFile(chemin_zip) as zf:
        noms_xml = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if len(noms_xml) != 1:
            raise SourceError(f"{len(noms_xml)} fichiers XML dans le ZIP au lieu d'un seul")

        with zf.open(noms_xml[0]) as flux:
            contexte = ET.iterparse(flux, events=("start", "end"))
            _, racine = next(contexte)
            if racine.tag != "pdv_liste":
                raise SourceError(f"balise racine <{racine.tag}> au lieu de <pdv_liste>")

            for evenement, elem in contexte:
                if evenement != "end" or elem.tag != "pdv":
                    continue
                attributs = (elem.get("id"), elem.get("latitude"), elem.get("longitude"),
                             elem.get("cp"), elem.get("pop"))
                # findtext renvoie None si la balise manque : la différence avec "" est gardée.
                station = attributs + (elem.findtext("adresse"), elem.findtext("ville"))
                releves = []
                for prix in elem.iter("prix"):
                    if not prix.attrib:
                        compteurs["prix_vides"] += 1  # <prix/> vide : station sans prix dans l'année, gardée telle quelle
                    releves.append(attributs + (prix.get("id"), prix.get("nom"),
                                                prix.get("maj"), prix.get("valeur")))
                yield station, releves
                # Sans ces deux clear(), l'arbre complet resterait en mémoire (plus de 5 millions de relevés).
                elem.clear()
                racine.clear()


class EcrivainParquet:
    """Écrit un Parquet par lots de TAILLE_LOT lignes, dans un fichier .part renommé à la fin.

    Les colonnes techniques ont la même valeur pour toutes les lignes d'un
    fichier : elles sont ajoutées au moment d'écrire chaque lot.
    """

    def __init__(self, entite: str, annee: int, techniques: tuple):
        dossier = RAW / entite / f"annee={annee}"
        dossier.mkdir(parents=True, exist_ok=True)
        self.dest = dossier / f"{entite}_{annee}.parquet"
        self.tmp = self.dest.with_suffix(".part")
        self.nb_colonnes = len(COLONNES[entite])
        self.schema = SCHEMAS[entite]
        self.techniques = techniques
        self.lot: list[tuple] = []
        self.writer = pq.ParquetWriter(self.tmp, self.schema, compression="zstd")

    def ajouter(self, ligne: tuple) -> None:
        self.lot.append(ligne)
        if len(self.lot) >= TAILLE_LOT:
            self.vider()

    def vider(self) -> None:
        if not self.lot:
            return
        n = len(self.lot)
        colonnes = [pa.array(c, type=pa.string()) for c in zip(*self.lot)]
        colonnes += [pa.array([v] * n, type=self.schema.field(self.nb_colonnes + i).type)
                     for i, v in enumerate(self.techniques)]
        self.writer.write_table(pa.table(colonnes, schema=self.schema))
        self.lot.clear()

    def terminer(self) -> Path:
        self.vider()
        self.writer.close()
        self.tmp.replace(self.dest)  # renommage atomique : jamais de Parquet incomplet sous le nom final
        return self.dest

    def abandonner(self) -> None:
        self.writer.close()
        self.tmp.unlink(missing_ok=True)  # pas de Parquet à moitié écrit


def ecrire_parquets(annee: int, chemin_zip: Path, sha256_source: str) -> tuple[dict, dict]:
    """Écrit les Parquet prix et stations de l'année ; renvoie leurs chemins et les compteurs."""
    compteurs = {"stations": 0, "prix": 0, "prix_vides": 0}
    techniques = (annee, chemin_zip.name, sha256_source, datetime.now(timezone.utc))
    ecrivains = {entite: EcrivainParquet(entite, annee, techniques) for entite in COLONNES}
    prochain_palier = TAILLE_LOT
    debut = time.perf_counter()

    try:
        for station, releves in lire_pdv(chemin_zip, compteurs):
            ecrivains["stations"].ajouter(station)
            compteurs["stations"] += 1
            for releve in releves:
                ecrivains["prix"].ajouter(releve)
            compteurs["prix"] += len(releves)
            if compteurs["prix"] >= prochain_palier:
                duree = time.perf_counter() - debut
                log.info("        %s relevés lus (%s par seconde)",
                         formater(compteurs["prix"]), formater(int(compteurs["prix"] / duree)))
                prochain_palier += TAILLE_LOT
        chemins = {entite: ecrivain.terminer() for entite, ecrivain in ecrivains.items()}
    except Exception:
        for ecrivain in ecrivains.values():
            ecrivain.abandonner()
        raise

    return chemins, compteurs


def verifier_prix(con, chemin_parquet: Path, annee: int, compteurs: dict) -> dict:
    """Contrôle le Parquet des prix ; lève SourceError si le fichier est inutilisable.

    Les anomalies qui n'empêchent pas le chargement sont signalées en
    avertissement : elles seront traitées dans dbt.
    """
    stats = con.execute(f"""
        SELECT
            count(*)                                                 AS releves,
            count(DISTINCT pdv_id) FILTER (maj IS NOT NULL)          AS stations,
            count(DISTINCT (pdv_id, prix_id)) FILTER (maj IS NOT NULL) AS couples,
            count(*) FILTER (maj IS NOT NULL AND left(maj, 4) <> '{annee}') AS hors_annee,
            min(maj)                                                 AS premier,
            max(maj)                                                 AS dernier
        FROM read_parquet('{chemin_parquet.as_posix()}')
    """).fetchone()
    stats = dict(zip(["releves", "stations", "couples", "hors_annee", "premier", "dernier"], stats))

    if stats["releves"] == 0 or stats["dernier"] is None:
        raise SourceError("aucun relevé de prix daté dans le fichier")

    log.info("Prix : %s relevés, %s stations avec prix, %s couples station × carburant",
             formater(stats["releves"]), formater(stats["stations"]), formater(stats["couples"]))
    log.info("Période : du %s au %s", stats["premier"], stats["dernier"])

    # Constat d'exploration : une station sans aucun prix dans l'année porte une seule balise <prix/> vide.
    if compteurs["prix_vides"]:
        log.warning("%s balises <prix/> vides (stations sans prix dans l'année), gardées avec des colonnes NULL",
                    formater(compteurs["prix_vides"]))
    if stats["hors_annee"]:
        log.warning("%s relevés datés hors de l'année %d", formater(stats["hors_annee"]), annee)

    # Pour l'année en cours, un dernier relevé trop ancien signale un fichier qui n'est plus mis à jour.
    if annee == date.today().year:
        retard = (date.today() - date.fromisoformat(stats["dernier"][:10])).days
        if retard > RETARD_MAX_JOURS:
            log.warning("Dernier relevé vieux de %d jours : le fichier annuel n'est peut-être plus mis à jour", retard)
        else:
            log.info("Dernier relevé vieux de %d jour(s) : fichier à jour", retard)
    return stats


def verifier_stations(con, chemin_parquet: Path) -> dict:
    """Contrôle le Parquet des stations ; lève SourceError si le fichier est inutilisable."""
    stats = con.execute(f"""
        SELECT
            count(*)                                                        AS stations,
            count(DISTINCT pdv_id)                                          AS identifiants,
            count(*) FILTER (adresse IS NULL OR trim(adresse) = '')         AS sans_adresse,
            count(*) FILTER (ville IS NULL OR trim(ville) = '')             AS sans_ville,
            count(*) FILTER (latitude IS NULL OR latitude = ''
                             OR longitude IS NULL OR longitude = '')        AS sans_coordonnees
        FROM read_parquet('{chemin_parquet.as_posix()}')
    """).fetchone()
    stats = dict(zip(["stations", "identifiants", "sans_adresse", "sans_ville", "sans_coordonnees"], stats))

    if stats["stations"] == 0:
        raise SourceError("aucune station dans le fichier")

    log.info("Stations : %s", formater(stats["stations"]))
    if stats["identifiants"] < stats["stations"]:
        log.warning("%s stations en double (même pdv_id)",
                    formater(stats["stations"] - stats["identifiants"]))
    for cle, libelle in [("sans_adresse", "sans adresse"), ("sans_ville", "sans ville"),
                         ("sans_coordonnees", "sans coordonnées")]:
        if stats[cle]:
            log.warning("%s stations %s", formater(stats[cle]), libelle)
    return stats


def date_telechargement(chemin_zip: Path) -> date:
    """Jour de téléchargement, lu dans le nom : PrixCarburants_annuel_2026_telecharge_20260928.zip."""
    return datetime.strptime(chemin_zip.stem.rsplit("_", 1)[-1], "%Y%m%d").date()


def nettoyer_archive() -> None:
    """Applique la règle de conservation des ZIP archivés, année par année.

    Le ZIP le plus récent est toujours gardé (il est réutilisé si le script est
    relancé dans la journée). En remontant le temps, on garde ensuite le dernier
    ZIP de chaque semaine ISO, sauf si son contenu (même empreinte) est déjà
    gardé : le fichier d'une année finie, retéléchargé à l'identique, n'est
    conservé qu'une fois. Sans cette règle, l'archive grossirait d'environ
    10 Go par an.
    """
    annees = sorted({int(z.name.split("_")[2])
                     for z in ARCHIVE.glob("PrixCarburants_annuel_*_telecharge_*.zip")})
    for annee in annees:
        zips = sorted(ARCHIVE.glob(f"PrixCarburants_annuel_{annee}_telecharge_*.zip"),
                      key=date_telechargement, reverse=True)
        semaines_vues, empreintes_gardees = set(), set()
        supprimes, octets = 0, 0
        for rang, chemin_zip in enumerate(zips):
            semaine = date_telechargement(chemin_zip).isocalendar()[:2]
            sha256_zip = empreinte(chemin_zip)
            # Du plus récent au plus ancien, le premier ZIP rencontré dans une semaine en est le dernier.
            dernier_de_sa_semaine = semaine not in semaines_vues
            semaines_vues.add(semaine)
            if rang == 0 or (dernier_de_sa_semaine and sha256_zip not in empreintes_gardees):
                empreintes_gardees.add(sha256_zip)
                continue
            octets += chemin_zip.stat().st_size
            chemin_zip.unlink()
            supprimes += 1
        log.info("Archive %d : %d ZIP gardés, %d supprimés (%.1f Mo libérés)",
                 annee, len(zips) - supprimes, supprimes, octets / 1e6)


def exposer(con) -> None:
    """(Re)crée les vues raw.prix et raw.stations sur tous les fichiers Parquet annuels.

    Les vues enregistrent le chemin absolu des Parquet : si le dossier du projet
    est déplacé, relancer ingest.py suffit à les recréer.
    """
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for entite in COLONNES:
        motif = (RAW / entite / "annee=*" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW raw.{entite} AS
            SELECT * FROM read_parquet('{motif}', hive_partitioning = false, union_by_name = true)
        """)
        for annee, lignes in con.execute(
            f"SELECT _source_year, count(*) FROM raw.{entite} GROUP BY 1 ORDER BY 1"
        ).fetchall():
            log.info("raw.%s, %d : %s lignes", entite, annee, formater(lignes))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestion des fichiers annuels des prix des carburants.")
    parser.add_argument("annees", nargs="*", type=int,
                        help="années à charger (par défaut : année en cours, N-1 début janvier, "
                             "années sans Parquet depuis PREMIERE_ANNEE)")
    parser.add_argument("--forcer", action="store_true",
                        help="retélécharger même si le ZIP du jour est déjà archivé")
    args = parser.parse_args()
    annees = {a: "imposée" for a in args.annees} if args.annees else choisir_annees(date.today())

    configurer_logs()
    log.info("=" * 60)
    log.info("Ingestion des prix des carburants : %s",
             ", ".join(f"{a} ({raison})" for a, raison in annees.items()))
    log.info("=" * 60)
    debut = time.perf_counter()
    bilan = []

    try:
        for annee in annees:
            debut_annee = time.perf_counter()
            with etape(f"[{annee}] Téléchargement"):
                chemin_zip = telecharger(annee, forcer=args.forcer)
            with etape(f"[{annee}] Calcul de l'empreinte"):
                sha256_source = empreinte(chemin_zip)
            with etape(f"[{annee}] Lecture du XML et écriture des Parquet"):
                chemins, compteurs = ecrire_parquets(annee, chemin_zip, sha256_source)
            with etape(f"[{annee}] Vérification des Parquet"), duckdb.connect() as con:
                stats_prix = verifier_prix(con, chemins["prix"], annee, compteurs)
                stats_stations = verifier_stations(con, chemins["stations"])
            bilan.append((annee, stats_prix, stats_stations, chemins, sha256_source,
                          time.perf_counter() - debut_annee))

        with etape("Mise à jour des vues raw.prix et raw.stations"), duckdb.connect(str(DB)) as con:
            exposer(con)
        with etape("Nettoyage de l'archive des ZIP"):
            nettoyer_archive()
    except Exception:
        log.error("=" * 60)
        log.error("Ingestion interrompue après %.2f s, voir le détail ci-dessus",
                  time.perf_counter() - debut)
        log.error("=" * 60)
        return 1

    log.info("=" * 60)
    log.info("Ingestion terminée")
    for annee, stats_prix, stats_stations, chemins, sha256_source, duree in bilan:
        taille = sum(c.stat().st_size for c in chemins.values()) / 1e6
        log.info("   - %d : %s relevés, %s stations, dernier relevé le %s, Parquet de %.1f Mo, "
                 "empreinte %s…, %.1f s",
                 annee, formater(stats_prix["releves"]), formater(stats_stations["stations"]),
                 stats_prix["dernier"], taille, sha256_source[:12], duree)
    log.info("   - Durée totale : %.2f s", time.perf_counter() - debut)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
