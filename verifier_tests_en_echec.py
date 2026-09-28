"""
=============================================================================
Vérification des tests : chaque test singulier doit échouer sur un défaut
=============================================================================
Objectif :
    Un test mal écrit peut passer à tous les coups. Pour chaque test
    singulier, ce script injecte un défaut précis, dans les données ou dans
    une copie du code dbt, relance ce seul test et vérifie qu'il le détecte.

    Tout se passe sur un échantillon : quelques dizaines de stations réelles,
    copiées dans une base DuckDB séparée (data/tests_en_echec/). Ni la base
    principale ni le projet dbt ne sont modifiés.

    Avant les scénarios, un témoin vérifie que tous les tests passent sur
    l'échantillon intact : un échec ne peut donc venir que du défaut injecté.

Utilisation :
    python verifier_tests_en_echec.py                 # tous les scénarios
    python verifier_tests_en_echec.py assert_age_des_prix_positif   # un seul

Prérequis :
    python ingest.py a déjà été lancé (vues raw.prix et raw.stations).
=============================================================================
"""

from contextlib import contextmanager
from pathlib import Path
import json
import logging
import os
import shutil
import subprocess
import sys
import time

import duckdb

RACINE = Path(__file__).resolve().parent
DB = RACINE / "data" / "carburant.duckdb"
DBT = RACINE / "dbt"
TRAVAIL = RACINE / "data" / "tests_en_echec"
LOGS = RACINE / "logs"
DBT_EXE = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")

NB_STATIONS_ECHANTILLON = 60
# Stations gardées dans l'échantillon pour leurs particularités (constats d'exploration) :
# deux relevés en conflit (24650001, 38480005) et la seule station avec pop = N (13500010).
STATIONS_IMPOSEES = ["24650001", "38480005", "13500010"]

# Premier relevé de prix d'une année, pour cibler une seule ligne.
UNE_LIGNE_2025 = "rowid = (SELECT min(rowid) FROM raw.prix WHERE prix_id IS NOT NULL AND _source_year = 2025)"
# Version 2026 d'une station qui a des prix en 2026.
UNE_STATION_2026 = """_source_year = 2026 AND pdv_id = (
    SELECT min(pdv_id) FROM raw.prix WHERE prix_id IS NOT NULL AND _source_year = 2026)"""

# Un scénario = un test, le défaut injecté, et le statut attendu.
#   sql       : requêtes appliquées aux tables raw de l'échantillon ;
#   code      : remplacements dans une copie du projet dbt {fichier: (avant, après)}.
SCENARIOS = [
    {"test": "assert_maj_toujours_lisible",
     "defaut": "un maj illisible (2025-13-45T25:00:00)",
     "sql": [f"UPDATE raw.prix SET maj = '2025-13-45T25:00:00' WHERE {UNE_LIGNE_2025}"]},
    {"test": "assert_maj_dans_annee_du_fichier",
     "defaut": "un relevé de 2024 dans le fichier 2025",
     "sql": [f"UPDATE raw.prix SET maj = '2024-06-01T10:00:00' WHERE {UNE_LIGNE_2025}"]},
    {"test": "assert_balises_prix_vides_seules",
     "defaut": "une balise <prix/> vide ajoutée à une station qui a des prix",
     "sql": ["""INSERT INTO raw.prix
                SELECT * REPLACE (NULL AS prix_id, NULL AS prix_nom, NULL AS maj, NULL AS valeur)
                FROM raw.prix WHERE prix_id IS NOT NULL LIMIT 1"""]},
    {"test": "assert_aucun_releve_pendant_heure_inexistante",
     "defaut": "un relevé à 02:30 la nuit du passage à l'heure d'été 2025",
     "sql": [f"UPDATE raw.prix SET maj = '2025-03-30T02:30:00' WHERE {UNE_LIGNE_2025}"]},
    {"test": "assert_conflits_de_prix_rares",
     "defaut": "11 relevés en conflit ajoutés (même instant, prix + 0,10 €)",
     "sql": ["""INSERT INTO raw.prix
                SELECT * REPLACE (CAST(CAST(valeur AS DECIMAL(5, 3)) + 0.100 AS VARCHAR) AS valeur)
                FROM raw.prix WHERE prix_id IS NOT NULL ORDER BY rowid LIMIT 11"""]},
    {"test": "assert_staging_conserve_les_releves",
     "defaut": "filtre en trop dans le staging : le SP98 disparaît",
     "code": {"models/staging/stg_roulez_eco__prix.sql":
              ("where prix_id is not null", "where prix_id is not null and prix_id <> '6'")}},
    {"test": "assert_un_prix_par_station_carburant_et_maj",
     "defaut": "départage des relevés en conflit retiré du staging",
     "code": {"models/staging/stg_roulez_eco__prix.sql": (") = 1", ") >= 1")}},
    {"test": "assert_prix_entre_0_30_et_4_euros",
     "defaut": "un prix en millièmes d'euro (1638 au lieu de 1.638)",
     "sql": [f"UPDATE raw.prix SET valeur = '1638' WHERE {UNE_LIGNE_2025}"]},
    {"test": "assert_une_ligne_par_station_et_annee",
     "defaut": "une station en double dans un fichier annuel",
     "sql": ["INSERT INTO raw.stations SELECT * FROM raw.stations ORDER BY rowid LIMIT 1"]},
    {"test": "assert_stations_avec_prix_en_metropole",
     "defaut": "latitude et longitude inversées pour une station avec prix",
     "sql": [f"UPDATE raw.stations SET latitude = longitude, longitude = latitude WHERE {UNE_STATION_2026}"]},
    {"test": "assert_mart_stations_en_metropole",
     "defaut": "coordonnées à 0 pour une station avec prix",
     "sql": [f"UPDATE raw.stations SET latitude = '0', longitude = '0' WHERE {UNE_STATION_2026}"]},
    {"test": "assert_changements_ont_un_prix_different",
     "defaut": "filtre des relevés répétés retiré du mart des changements",
     "code": {"models/marts/mart_changements_prix.sql":
              ("qualify prix_litre is distinct from lag(prix_litre) over releves_du_couple", "qualify true")}},
    {"test": "assert_un_premier_releve_par_couple",
     "defaut": "historique partitionné par station seulement, sans le carburant",
     "code": {"models/marts/mart_changements_prix.sql":
              ("partition by station_id, carburant_id order by maj_at)\n",
               "partition by station_id order by maj_at)\n")}},
    {"test": "assert_un_prix_actuel_par_station_et_carburant",
     "defaut": "les deux derniers prix gardés au lieu du dernier",
     "code": {"models/marts/mart_prix_actuels.sql": ("order by maj_at desc) = 1", "order by maj_at desc) <= 2")}},
    {"test": "assert_prix_actuel_egal_dernier_changement",
     "defaut": "le premier prix pris au lieu du dernier",
     "code": {"models/marts/mart_prix_actuels.sql": ("order by maj_at desc) = 1", "order by maj_at asc) = 1")}},
    {"test": "assert_age_des_prix_positif",
     "defaut": "date de référence prise au premier relevé au lieu du dernier",
     "code": {"models/marts/mart_prix_actuels.sql": ("select max(maj_at) as reference_at", "select min(maj_at) as reference_at")}},
    {"test": "assert_aucun_releve_dans_le_futur",
     "defaut": "un relevé de 2026 daté du 31/12/2026, après le téléchargement du fichier",
     "sql": ["""UPDATE raw.prix SET maj = '2026-12-31T12:00:00'
                WHERE rowid = (SELECT min(rowid) FROM raw.prix WHERE prix_id IS NOT NULL AND _source_year = 2026)"""]},
    {"test": "assert_prix_suspects_rares",
     "defaut": "tous les prix d'E85 passés à 1,99 € (niveau de l'essence)",
     "sql": ["UPDATE raw.prix SET valeur = '1.990' WHERE prix_id = '3'"],
     "attendu": "warn"},
]

log = logging.getLogger("tests_en_echec")


def configurer_logs() -> None:
    """Écrit les messages à la fois dans le terminal et dans logs/verifier_tests_en_echec.log."""
    LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS / "verifier_tests_en_echec.log", encoding="utf-8"),
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


def preparer_echantillon() -> Path:
    """Copie un échantillon de stations réelles dans data/tests_en_echec/echantillon.duckdb.

    Les tables raw.prix et raw.stations de l'échantillon ont exactement les
    colonnes des vues raw de la base principale.
    """
    if TRAVAIL.exists():
        shutil.rmtree(TRAVAIL)
    TRAVAIL.mkdir(parents=True)
    echantillon = TRAVAIL / "echantillon.duckdb"

    with duckdb.connect(str(echantillon)) as con:
        con.execute(f"ATTACH '{DB.as_posix()}' AS source (READ_ONLY)")
        con.execute("CREATE SCHEMA raw")
        # Stations tirées de façon reproductible (ordre de l'empreinte md5) : des stations
        # avec prix les deux années, les stations imposées, et quelques stations sans prix.
        con.execute(f"""
            CREATE TEMP TABLE choix AS
            (SELECT pdv_id FROM source.raw.prix WHERE prix_id IS NOT NULL
             GROUP BY pdv_id HAVING count(DISTINCT _source_year) = 2
             ORDER BY md5(pdv_id) LIMIT {NB_STATIONS_ECHANTILLON})
            UNION
            (SELECT pdv_id FROM source.raw.prix GROUP BY pdv_id HAVING count(prix_id) = 0
             ORDER BY md5(pdv_id) LIMIT 5)
            UNION
            SELECT unnest(?::VARCHAR[])
        """, [STATIONS_IMPOSEES])
        for entite in ("prix", "stations"):
            con.execute(f"""
                CREATE TABLE raw.{entite} AS
                SELECT * FROM source.raw.{entite} WHERE pdv_id IN (SELECT pdv_id FROM choix)
            """)
        stations, releves, e85 = con.execute("""
            SELECT (SELECT count(DISTINCT pdv_id) FROM raw.stations),
                   (SELECT count(*) FROM raw.prix),
                   (SELECT count(*) FROM raw.prix WHERE prix_id = '3')
        """).fetchone()

    if e85 == 0:
        raise RuntimeError("aucun relevé d'E85 dans l'échantillon : le scénario des prix suspects serait vide")
    log.info("Échantillon : %d stations, %d relevés (dont %d d'E85)", stations, releves, e85)
    return echantillon


def lancer_dbt(nom: str, echantillon: Path, sql: list[str], code: dict, selection: list[str]) -> dict:
    """Applique le défaut sur une copie de l'échantillon et du projet dbt, lance dbt build.

    Renvoie le statut de chaque test exécuté, d'après target/run_results.json.
    """
    dossier = TRAVAIL / nom
    base = dossier / "carburant.duckdb"
    projet = dossier / "dbt"
    dossier.mkdir(parents=True, exist_ok=True)
    shutil.copy(echantillon, base)
    shutil.copytree(DBT, projet, ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"))

    with duckdb.connect(str(base)) as con:
        for requete in sql:
            con.execute(requete)

    for fichier, (avant, apres) in code.items():
        chemin = projet / fichier
        texte = chemin.read_text(encoding="utf-8")
        # Le remplacement doit toucher exactement un endroit, sinon le défaut n'est pas celui décrit.
        if texte.count(avant) != 1:
            raise RuntimeError(f"{fichier} : {texte.count(avant)} occurrences de {avant!r} au lieu d'une")
        chemin.write_text(texte.replace(avant, apres), encoding="utf-8")

    commande = [str(DBT_EXE), "build", "--project-dir", str(projet), "--profiles-dir", str(projet)] + selection
    env = {**os.environ, "CARBURANT_DB": base.as_posix(), "PYTHONIOENCODING": "utf-8"}
    sortie = subprocess.run(commande, cwd=projet, env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    (dossier / "dbt_build.log").write_text(sortie.stdout + sortie.stderr, encoding="utf-8")

    resultats = projet / "target" / "run_results.json"
    if not resultats.is_file():
        raise RuntimeError(f"dbt n'a produit aucun résultat, voir {dossier / 'dbt_build.log'}")
    return {r["unique_id"].split(".")[-1] if r["unique_id"].startswith("test.") else r["unique_id"]: r["status"]
            for r in json.loads(resultats.read_text(encoding="utf-8"))["results"]}


def verifier_temoin(echantillon: Path) -> None:
    """Tous les modèles et tous les tests doivent passer sur l'échantillon intact."""
    statuts = lancer_dbt("temoin", echantillon, sql=[], code={}, selection=[])
    anormaux = {noeud: statut for noeud, statut in statuts.items() if statut not in ("pass", "success")}
    log.info("Témoin : %d modèles et tests exécutés", len(statuts))
    if anormaux:
        raise RuntimeError(f"l'échantillon intact ne passe pas tous les tests : {anormaux}")


def verifier_scenario(scenario: dict, echantillon: Path) -> bool:
    """Injecte le défaut du scénario et vérifie que son test le détecte."""
    test = scenario["test"]
    attendu = scenario.get("attendu", "fail")
    # « +test » : le test et tous les modèles dont il dépend ; « empty » : sans les autres tests
    # de ces modèles, pour ne juger que le test visé.
    statuts = lancer_dbt(test, echantillon, scenario.get("sql", []), scenario.get("code", {}),
                         ["--select", f"+{test}", "--indirect-selection", "empty"])
    obtenu = statuts.get(test, "absent")
    log.info("Défaut : %s -> statut %s (attendu : %s)", scenario["defaut"], obtenu, attendu)
    return obtenu == attendu


def main() -> int:
    configurer_logs()
    choisis = [s for s in SCENARIOS if not sys.argv[1:] or s["test"] in sys.argv[1:]]
    inconnus = set(sys.argv[1:]) - {s["test"] for s in SCENARIOS}
    if inconnus:
        print(f"Scénarios inconnus : {sorted(inconnus)}")
        return 1

    log.info("=" * 60)
    log.info("Vérification des tests singuliers : %d scénarios", len(choisis))
    log.info("=" * 60)
    debut = time.perf_counter()
    bilan = []

    try:
        with etape("Préparation de l'échantillon"):
            echantillon = preparer_echantillon()
        with etape("Témoin : tous les tests passent sur l'échantillon intact"):
            verifier_temoin(echantillon)
        for scenario in choisis:
            with etape(f"Scénario {scenario['test']}"):
                bilan.append((scenario, verifier_scenario(scenario, echantillon)))
    except Exception:
        log.error("=" * 60)
        log.error("Vérification interrompue après %.2f s, voir le détail ci-dessus",
                  time.perf_counter() - debut)
        log.error("=" * 60)
        return 1

    non_detectes = [s["test"] for s, detecte in bilan if not detecte]
    log.info("=" * 60)
    for scenario, detecte in bilan:
        niveau = logging.INFO if detecte else logging.ERROR
        log.log(niveau, "   %s %s : %s", "[détecté]    " if detecte else "[NON DÉTECTÉ]",
                scenario["test"], scenario["defaut"])
    log.info("   - %d défauts détectés sur %d, en %.1f s",
             len(bilan) - len(non_detectes), len(bilan), time.perf_counter() - debut)
    log.info("=" * 60)
    return 1 if non_detectes else 0


if __name__ == "__main__":
    sys.exit(main())
