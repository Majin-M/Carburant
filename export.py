"""
=============================================================================
Export : marts → fichiers JSON pour le portfolio
=============================================================================
Objectif :
    Lit les marts de data/carburant.duckdb et écrit dans exports/ :
      - prix_actuels.json : une entrée par station, avec ses coordonnées,
        son adresse et le dernier prix de chaque carburant. Format compact :
        chaque station et chaque prix est un tableau, dont l'ordre des valeurs
        est donné une seule fois par colonnes_station et colonnes_prix ;
      - metadata.json     : date des données, fichiers source et empreintes,
        volumes, règles de lecture et résumé de la dernière exécution dbt.

    Le portfolio calcule lui-même les distances dans le navigateur : la
    position de la personne n'est ni envoyée ni stockée.

Utilisation :
    python export.py

Attention :
    Les fichiers JSON sont entièrement remplacés à chaque exécution.
    dbt build doit avoir été lancé avant (marts et dbt/target/run_results.json).
=============================================================================
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import sys
import time

import duckdb

RACINE = Path(__file__).resolve().parent
DB = RACINE / "data" / "carburant.duckdb"
EXPORTS = RACINE / "exports"
RUN_RESULTS = RACINE / "dbt" / "target" / "run_results.json"
LOGS = RACINE / "logs"

RETARD_MAX_JOURS = 2          # au-delà, les données exportées sont suspectes
JOURS_PRIX_RECENT = 7         # règle de lecture transmise au portfolio : griser au-delà

CARBURANTS = {1: "Gazole", 2: "SP95", 3: "E85", 4: "GPLc", 5: "E10", 6: "SP98"}

# Ordre des valeurs dans chaque station et dans chaque prix de prix_actuels.json.
# Les noms de clés ne sont écrits qu'une fois : le fichier pèse 2 fois moins
# qu'avec un objet par station et par prix.
COLONNES_STATION = ["id", "latitude", "longitude", "adresse", "ville", "code_postal", "autoroute", "prix"]
COLONNES_PRIX = ["carburant_id", "prix", "maj", "age_jours", "suspect"]

log = logging.getLogger("export")


class ExportError(ValueError):
    """Les marts ne permettent pas un export fiable (vides, incohérents…)."""


def configurer_logs() -> None:
    """Écrit les messages à la fois dans le terminal et dans logs/export.log."""
    LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS / "export.log", encoding="utf-8"),
        ],
    )


def formater(nombre: int) -> str:
    """Formate un entier à la française : 37039 -> '37 039'."""
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


def lire_stations(con) -> list[list]:
    """Une ligne par station (ordre COLONNES_STATION), avec ses prix (ordre COLONNES_PRIX).

    Les instants sont écrits en UTC, à la minute (2026-09-24T22:42Z) : le
    navigateur les affiche dans le fuseau de la personne, sans ambiguïté au
    changement d'heure.
    """
    lignes = con.execute("""
        SELECT
            s.station_id,
            round(s.latitude, 5)                                   AS latitude,
            round(s.longitude, 5)                                  AS longitude,
            s.adresse,
            s.ville,
            s.code_postal,
            s.est_autoroute,
            list({
                'carburant_id': p.carburant_id,
                'prix': CAST(p.prix_litre AS DOUBLE),
                'maj': strftime(p.maj_at AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%MZ'),
                'age_jours': p.nombre_jours_depuis_maj,
                'suspect': p.est_prix_suspect
            } ORDER BY p.carburant_id)                             AS prix
        FROM marts.mart_stations AS s
        JOIN marts.mart_prix_actuels AS p USING (station_id)
        GROUP BY ALL
        ORDER BY s.station_id
    """).fetchall()
    # DuckDB renvoie chaque prix comme un dict : on le réduit à un tableau dans l'ordre COLONNES_PRIX.
    return [list(ligne[:-1]) + [[[p[c] for c in COLONNES_PRIX] for p in ligne[-1]]] for ligne in lignes]


def lire_resume(con) -> dict:
    """Date des données, fichiers source et volumes, lus dans les marts et la couche raw."""
    reference_at, prix_actuels, prix_suspects, prix_recents = con.execute(f"""
        SELECT
            strftime(any_value(reference_at) AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ'),
            count(*),
            count(*) FILTER (est_prix_suspect),
            count(*) FILTER (nombre_jours_depuis_maj <= {JOURS_PRIX_RECENT})
        FROM marts.mart_prix_actuels
    """).fetchone()
    # raw.stations porte les mêmes colonnes techniques que raw.prix, pour 500 fois moins de lignes.
    fichiers = con.execute("""
        SELECT DISTINCT
            _source_year,
            _source_file,
            _source_sha256,
            strftime(_loaded_at AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ')
        FROM raw.stations
        ORDER BY _source_year
    """).fetchall()
    changements, stations = con.execute("""
        SELECT (SELECT count(*) FROM marts.mart_changements_prix),
               (SELECT count(*) FROM marts.mart_stations)
    """).fetchone()
    return {
        "reference_at": reference_at,
        "fichiers_source": [
            {"annee": a, "fichier": f, "sha256": h, "charge_le": c} for a, f, h, c in fichiers
        ],
        "volumes": {
            "stations": stations,
            "prix_actuels": prix_actuels,
            "prix_actuels_recents": prix_recents,
            "prix_suspects": prix_suspects,
            "changements_de_prix": changements,
        },
    }


def verifier(stations: list[list], resume: dict) -> None:
    """Lève ExportError si l'export est inutilisable ; avertit si les données sont anciennes."""
    if not stations:
        raise ExportError("aucune station à exporter")
    i = {nom: n for n, nom in enumerate(COLONNES_STATION)}
    sans_coordonnees = [s[i["id"]] for s in stations if s[i["latitude"]] is None or s[i["longitude"]] is None]
    if sans_coordonnees:
        raise ExportError(f"{len(sans_coordonnees)} stations sans coordonnées, dont {sans_coordonnees[:5]}")
    carburants_inconnus = {p[0] for s in stations for p in s[i["prix"]]} - set(CARBURANTS)
    if carburants_inconnus:
        raise ExportError(f"carburants inconnus : {sorted(carburants_inconnus)}")

    volumes = resume["volumes"]
    log.info("Stations : %s, prix actuels : %s, dont %s de %d jours ou moins et %s suspects",
             formater(len(stations)), formater(volumes["prix_actuels"]),
             formater(volumes["prix_actuels_recents"]), JOURS_PRIX_RECENT, formater(volumes["prix_suspects"]))

    reference = datetime.fromisoformat(resume["reference_at"].replace("Z", "+00:00"))
    retard = (datetime.now(timezone.utc) - reference).days
    if retard > RETARD_MAX_JOURS:
        log.warning("Données arrêtées au %s, il y a %d jours : relancer l'ingestion ?", resume["reference_at"], retard)
    else:
        log.info("Données arrêtées au %s", resume["reference_at"])


def lire_execution_dbt() -> dict | None:
    """Résumé de la dernière exécution dbt : commande, durée, modèles et tests par statut."""
    if not RUN_RESULTS.is_file():
        log.warning("Pas de %s : résumé dbt absent de metadata.json", RUN_RESULTS.relative_to(RACINE))
        return None
    resultats = json.loads(RUN_RESULTS.read_text(encoding="utf-8"))
    par_type: dict = {}
    for r in resultats["results"]:
        type_noeud = r["unique_id"].split(".")[0]          # model, test…
        par_type.setdefault(type_noeud, {}).setdefault(r["status"], 0)
        par_type[type_noeud][r["status"]] += 1
    execution = {
        "commande": resultats["args"].get("which"),
        "selection": resultats["args"].get("select") or "tout le projet",
        "genere_le": resultats["metadata"]["generated_at"],
        "duree_s": round(resultats["elapsed_time"], 1),
        "modeles": par_type.get("model", {}),
        "tests": par_type.get("test", {}),
    }
    log.info("Dernière exécution dbt : %s, modèles %s, tests %s",
             execution["commande"], execution["modeles"], execution["tests"])
    if execution["selection"] != "tout le projet":
        log.warning("La dernière exécution dbt ne portait que sur %s", execution["selection"])
    return execution


def ecrire_json(nom: str, contenu) -> Path:
    """Écrit exports/<nom> de façon atomique et renvoie son chemin."""
    EXPORTS.mkdir(exist_ok=True)
    dest = EXPORTS / nom
    tmp = dest.with_suffix(".part")
    # ensure_ascii=False garde les accents lisibles ; separators compacts : fichier plus léger.
    tmp.write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(dest)  # renommage atomique : le portfolio ne lit jamais un fichier à moitié écrit
    log.info("%s : %.2f Mo", nom, dest.stat().st_size / 1e6)
    return dest


def main() -> int:
    configurer_logs()
    log.info("=" * 60)
    log.info("Export des prix des carburants pour le portfolio")
    log.info("=" * 60)
    debut = time.perf_counter()

    try:
        with duckdb.connect(str(DB), read_only=True) as con:
            with etape("Lecture des stations et des prix actuels"):
                stations = lire_stations(con)
            with etape("Lecture de la date des données et des volumes"):
                resume = lire_resume(con)
        with etape("Vérification de l'export"):
            verifier(stations, resume)
        with etape("Lecture du résumé de la dernière exécution dbt"):
            execution_dbt = lire_execution_dbt()
        with etape("Écriture des fichiers JSON"):
            ecrire_json("prix_actuels.json", {
                "reference_at": resume["reference_at"],
                "colonnes_station": COLONNES_STATION,
                "colonnes_prix": COLONNES_PRIX,
                "stations": stations,
            })
            ecrire_json("metadata.json", {
                "genere_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                **resume,
                "source": {
                    "producteur": "Ministère de l'Économie, prix-carburants.gouv.fr",
                    "url": "https://donnees.roulez-eco.fr/opendata/annee",
                    "licence": "Licence Ouverte (Etalab)",
                },
                "carburants": {str(k): v for k, v in CARBURANTS.items()},
                "regles_de_lecture": [
                    "Les instants (maj, reference_at) sont en UTC ; les afficher dans le fuseau de la personne.",
                    "age_jours est compté depuis reference_at, le dernier relevé des données, pas depuis l'heure de lecture.",
                    f"Un prix de plus de {JOURS_PRIX_RECENT} jours est à afficher grisé.",
                    "Un prix suspect (E85 ou GPLc au niveau de l'essence) ne doit pas être présenté comme le moins cher.",
                    "Les stations couvrent la France métropolitaine et la Corse ; aucune station d'outre-mer n'a de prix.",
                    "La casse des villes est celle de la source, parfois en majuscules : à normaliser à l'affichage.",
                ],
                "derniere_execution_dbt": execution_dbt,
            })
    except Exception:
        log.error("=" * 60)
        log.error("Export interrompu après %.2f s, voir le détail ci-dessus", time.perf_counter() - debut)
        log.error("=" * 60)
        return 1

    log.info("=" * 60)
    log.info("Export terminé")
    log.info("   - Stations exportées : %s", formater(len(stations)))
    log.info("   - Données arrêtées au : %s", resume["reference_at"])
    log.info("   - Durée totale : %.2f s", time.perf_counter() - debut)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
