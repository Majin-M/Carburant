# Conventions de nommage

Règles de nommage des fichiers, schémas, tables, colonnes et scripts du projet. Elles reprennent celles du projet des prénoms, avec les ajustements imposés par une source XML.

## Principes généraux

- **snake_case** : lettres minuscules, mots séparés par `_`.
- **Pas d'accents ni d'espaces** dans les noms d'objets : `annee`, pas `année`.
- **Pas de mots réservés SQL** comme noms de colonnes (`year`, `order`, `group`…).
- **Langue** : les colonnes métier sont en français, avec le vocabulaire de la source quand il est clair (`maj`, `valeur`, `pop`). Les colonnes techniques sont en anglais, comme le veut l'usage dans dbt.

## Fichiers de données

| Fichier | Nom | Exemple |
|---|---|---|
| ZIP d'origine | `PrixCarburants_annuel_<année>_telecharge_<AAAAMMJJ>.zip`, dans `data/archive/` : le nom du serveur, suivi du jour de téléchargement | `PrixCarburants_annuel_2026_telecharge_20260928.zip` |
| Parquet `raw` | `data/raw/<entité>/annee=<année>/<entité>_<année>.parquet` : un dossier par entité et par année, au format `cle=valeur` reconnu par DuckDB et Spark | `data/raw/prix/annee=2026/prix_2026.parquet`, `data/raw/stations/annee=2026/stations_2026.parquet` |
| Fichier temporaire | Nom final suivi de `.part`, renommé une fois le fichier complet | `prix_2026.part` |
| ZIP publié | Nom du ZIP archivé, suivi des 12 premiers caractères de son empreinte sha256, dans la release `archive-<année>` | `PrixCarburants_annuel_2026_telecharge_20260927_41d81caea24b.zip` |

## Schémas

| Schéma | Contenu | Alimenté par |
|---|---|---|
| `raw` | Données source telles quelles | `ingest.py` (vue sur les Parquet) |
| `staging` | Données nettoyées et typées, un modèle par source | dbt |
| `marts` | Tables prêtes pour l'analyse et l'export | dbt |

## Tables

### `raw`

- **`<entité>`** : le nom de l'entité, sans préfixe. Le schéma `raw` suffit à indiquer la couche.
- Les colonnes gardent leur nom d'origine et restent en texte, comme dans le XML.
- **Exception propre au XML** : un relevé réunit les attributs de deux balises, `<pdv>` et `<prix>`, qui ont toutes deux un attribut `id`, et un attribut `nom` pour `<prix>`. Ces attributs sont préfixés par leur balise : `pdv_id`, `prix_id`, `prix_nom`. Les autres gardent leur nom exact (`latitude`, `cp`, `maj`, `valeur`…).
- Exemples : `raw.prix`, `raw.stations`.

### `staging`

- **`stg_<source>__<entité>`**, matérialisé en vue, avec un double underscore entre la source et l'entité, selon la convention dbt. La source est `roulez_eco`, du nom du serveur de données.
- C'est ici que les colonnes sont renommées et typées. Par exemple, `pdv_id` (texte) devient `station_id` (entier), et `maj` (texte, heure de Paris) devient `maj_at` (horodatage avec fuseau).
- Exemples : `staging.stg_roulez_eco__prix`, `staging.stg_roulez_eco__stations`.

### `marts`

- **`mart_<sujet>`** : un nom qui dit à quelle question la table répond.
- Exemples : `marts.mart_changements_prix`, `marts.mart_prix_actuels`, `marts.mart_stations`.

## Colonnes

### Colonnes techniques

- Préfixe **`_`** : ces colonnes décrivent le chargement, pas la donnée.
- On les repère ainsi tout de suite, et elles restent en fin de table.

| Colonne | Type | Signification |
|---|---|---|
| `_source_year` | `SMALLINT` | Année du fichier annuel chargé |
| `_source_file` | `VARCHAR` | Nom du ZIP archivé d'où vient la ligne |
| `_source_sha256` | `VARCHAR` | Empreinte sha256 de ce ZIP |
| `_loaded_at` | `TIMESTAMP WITH TIME ZONE` | Date et heure du chargement, en UTC |

### Préfixes et suffixes

| Préfixe ou suffixe | Signification | Exemple |
|---|---|---|
| `_id` (suffixe) | Identifiant de la source | `station_id`, `carburant_id` |
| `_at` (suffixe) | Horodatage avec fuseau horaire | `maj_at`, `_loaded_at` |
| `code_` (préfixe) | Code officiel | `code_postal` |
| `nombre_` (préfixe) | Comptage | `nombre_releves` |
| `part_` (préfixe) | Proportion, entre 0 et 1 | `part_releves_repetes` |
| `est_` (préfixe) | Booléen | `est_autoroute` |

Un horodatage sans fuseau ne reçoit jamais le suffixe `_at` : `maj` reste `maj` dans `raw`, où il est en heure de Paris sans indication de fuseau.

## Variables et macros dbt

- **Variables** : en snake_case, dans `dbt_project.yml`, avec un commentaire qui justifie leur valeur. Exemple : `prix_max_plausible_e85`.
- **Macros** : nommées comme la colonne qu'elles produisent quand elles en produisent une. Exemple : la macro `est_prix_suspect` produit la colonne `est_prix_suspect`.

## Fichiers exportés

- Clés JSON en snake_case, courtes, décrites dans le [catalogue](catalogue_de_donnees.md) : `age_jours`, `suspect`, `autoroute`. Elles forment l'interface avec le portfolio et ne suivent pas les préfixes des tables (`est_`, `nombre_`).
- Instants en UTC, au format ISO 8601 avec le suffixe `Z` : `2026-09-24T22:42Z`.

## Tests dbt

- Tests singuliers : **`assert_<règle vérifiée>`**, dans `dbt/tests/`. Le nom dit ce qui doit être vrai : `assert_un_prix_par_station_carburant_et_maj`.
- Chaque fichier commence par un commentaire qui cite le constat d'exploration ou la règle à l'origine du test.

## Scripts Python

- Un script par étape du pipeline, nommé d'après son rôle : `ingest.py`, `export.py`, `publier_archive.py`. `run.ps1` enchaîne les deux premiers avec dbt ; `verifier_tests_en_echec.py` vérifie que chaque test singulier détecte son défaut.
- Les fonctions portent un verbe à l'infinitif : `telecharger`, `lire_pdv`, `ecrire_parquets`, `verifier_prix`.
- Les constantes de configuration sont en majuscules en haut du fichier : `URL_ANNEE`, `RAW`, `DB`.
- Chaque étape est enveloppée dans `with etape("…")`, qui écrit `[DÉBUT]`, `[OK]` avec la durée, ou `[ÉCHEC]` avec la trace complète.
