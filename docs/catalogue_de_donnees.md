# Catalogue de données

Description des fichiers et des tables produits par le pipeline, de la source aux fichiers exportés. Les volumes correspondent aux fichiers annuels 2025 (complet) et 2026 (téléchargé le 28/09/2026, relevés jusqu'au 27/09 à 23:59).

## Vue d'ensemble

| Couche | Objet | Type | Grain | Lignes |
|---|---|---|---|---|
| archive | `data/archive/PrixCarburants_annuel_<année>_telecharge_<AAAAMMJJ>.zip` | fichier ZIP | une année, un jour de téléchargement | |
| archive | release GitHub `archive-<année>`, fichier `PrixCarburants_annuel_<année>_telecharge_<AAAAMMJJ>_<sha256, 12 caractères>.zip` | fichier ZIP | une année, une version | |
| `raw` | `data/raw/prix/annee=<année>/prix_<année>.parquet` | fichier Parquet | une balise `<prix>` | 5 302 458 (2025), 4 172 763 (2026) |
| `raw` | `raw.prix` | vue DuckDB sur tous les Parquet | une balise `<prix>` | 9 475 221 |
| `raw` | `data/raw/stations/annee=<année>/stations_<année>.parquet` | fichier Parquet | une balise `<pdv>` | 14 420 (2025), 14 793 (2026) |
| `raw` | `raw.stations` | vue DuckDB sur tous les Parquet | une balise `<pdv>` | 29 213 |
| `staging` | `staging.stg_roulez_eco__prix` | vue dbt | une station, un carburant, un instant de relevé | 9 465 583 |
| `staging` | `staging.stg_roulez_eco__stations` | vue dbt | une station, un fichier annuel | 29 213 |
| `marts` | `marts.mart_changements_prix` | table dbt | une station, un carburant, un changement de prix | 5 222 646 |
| `marts` | `marts.mart_stations` | table dbt | une station ayant publié au moins un prix | 10 112 |
| `marts` | `marts.mart_prix_actuels` | table dbt | une station, un carburant | 37 039 |

## ZIP archivés

Fichiers téléchargés depuis `https://donnees.roulez-eco.fr/opendata/annee/<année>`, gardés tels quels. Chaque ZIP contient un seul fichier `PrixCarburants_annuel_<année>.xml`, encodé en ISO-8859-1.

| Année | ZIP | XML décompressé |
|---|---|---|
| 2025 | 31,7 Mo | 386 Mo |
| 2026 (au 27/09) | 28,5 Mo | 322 Mo |

Le fichier de l'année en cours change chaque jour : un nouveau ZIP est archivé à chaque jour de téléchargement. Le ZIP d'où vient chaque ligne de `raw` est indiqué dans `_source_file`.

**Conservation** : `ingest.py` garde, pour chaque année, le ZIP le plus récent et le dernier ZIP de chaque semaine dont le contenu (empreinte sha256) n'est pas déjà gardé. Sur GitHub Actions, `publier_archive.py` publie dans la release `archive-<année>` le ZIP du dimanche de l'année en cours et toute version au contenu nouveau d'une année passée. Le nom publié se termine par les 12 premiers caractères de l'empreinte.

## `raw.prix`

Vue DuckDB sur les fichiers Parquet annuels, écrits par `ingest.py`. Une ligne par balise `<prix>` du XML, avec les attributs de la station (`<pdv>`) qui la contient. Les attributs sont gardés en texte, sous leur nom d'origine ; seuls `id` et `nom`, présents sur les deux balises, sont préfixés par leur balise.

| Colonne | Type | Source | Description | Exemple |
|---|---|---|---|---|
| `pdv_id` | VARCHAR | `<pdv id>` | Identifiant de la station, stable d'une année à l'autre | `1000001` |
| `latitude` | VARCHAR | `<pdv latitude>` | Latitude en degrés × 100 000 | `4620100` |
| `longitude` | VARCHAR | `<pdv longitude>` | Longitude en degrés × 100 000 | `519800` |
| `cp` | VARCHAR | `<pdv cp>` | Code postal, 5 caractères | `01000` |
| `pop` | VARCHAR | `<pdv pop>` | `R` route, `A` autoroute ; une station porte `N` | `R` |
| `prix_id` | VARCHAR | `<prix id>` | Carburant : `1` Gazole, `2` SP95, `3` E85, `4` GPLc, `5` E10, `6` SP98 | `1` |
| `prix_nom` | VARCHAR | `<prix nom>` | Nom du carburant | `Gazole` |
| `maj` | VARCHAR | `<prix maj>` | Date et heure du relevé, en heure de Paris, sans fuseau | `2026-09-25T00:42:00` |
| `valeur` | VARCHAR | `<prix valeur>` | Prix en euros par litre, point décimal (en millièmes d'euro, sans point, dans les anciens fichiers : vérifié sur 2015 et 2021 ; décimal de 2022 à 2026) | `2.424` |
| `_source_year` | SMALLINT | | Année du fichier chargé | `2026` |
| `_source_file` | VARCHAR | | Nom du ZIP archivé | `PrixCarburants_annuel_2026_telecharge_20260928.zip` |
| `_source_sha256` | VARCHAR | | Empreinte sha256 du ZIP | `41d81caea24b…` |
| `_loaded_at` | TIMESTAMP WITH TIME ZONE | | Date et heure du chargement | `2026-09-28 10:37:30+00` |

**Volumes**

| | 2025 | 2026 (au 27/09) |
|---|---|---|
| Lignes | 5 302 458 | 4 172 763 |
| dont relevés de prix | 5 297 800 | 4 167 785 |
| dont balises `<prix/>` vides | 4 658 | 4 978 |
| Stations avec au moins un prix | 9 726 | 9 774 |
| Couples station × carburant | 34 779 | 35 478 |
| Parquet (zstd) | 16,4 Mo | 13,7 Mo |

| Carburant (`prix_id`) | Relevés 2025 et 2026 |
|---|---|
| `1` Gazole | 2 757 638 |
| `5` E10 | 2 401 807 |
| `6` SP98 | 2 256 152 |
| `3` E85 | 1 052 145 |
| `2` SP95 | 509 774 |
| `4` GPLc | 488 069 |

**À savoir**

- **Le grain n'est pas unique.** Un même couple station × carburant a en moyenne plus de 100 relevés par an, parfois plusieurs dans la journée. 47 % des relevés répètent la valeur précédente du même couple : les vrais changements sont calculés dans `mart_changements_prix`.
- **Balises vides** : une station sans aucun prix dans l'année porte une seule balise `<prix/>` vide, jamais à côté d'un vrai prix. Sa ligne a toutes les colonnes `prix_id` à `valeur` à NULL. Les lignes sans coordonnées (69 en 2025, 68 en 2026) sont toutes des balises vides.
- **Deux relevés en conflit** : un seul couple par année a deux relevés au même `maj` avec deux valeurs différentes (station `24650001`, E10, `2025-09-05T08:33:38` : 1,56 et 1,566 ; station `38480005`, Gazole, `2026-01-28T06:00:00` : 1,899 et 1,919). Aucune information ne permet de savoir lequel est le bon.
- **`maj` est en heure de Paris**, sans fuseau : vérifié sur les traitements automatiques qui gardent leur heure locale toute l'année (voir le README). Le staging le convertit en horodatage avec fuseau.
- **`pop` vaut `N` pour une seule station** (`13500010`, Martigues), en 2025 comme en 2026 : valeur non documentée.
- **Prix ronds** : 642 relevés de 2025 valent exactement `1`, `2` ou `3` €, probablement des valeurs de remplissage. À ne pas confondre avec les prix suspects d'E85 et de GPLc, marqués dans les marts.
- **Pas de nom ni d'enseigne de station** dans la source : seulement l'adresse et la ville, chargées dans `raw.stations`.

## `raw.stations`

Vue DuckDB sur les fichiers Parquet annuels des stations, écrits par `ingest.py` pendant la même lecture du XML que les prix. Une ligne par balise `<pdv>`, avec le texte de ses balises `<adresse>` et `<ville>`. Les colonnes techniques sont les mêmes que dans `raw.prix`.

| Colonne | Type | Source | Description | Exemple |
|---|---|---|---|---|
| `pdv_id` | VARCHAR | `<pdv id>` | Identifiant de la station | `1000001` |
| `latitude` | VARCHAR | `<pdv latitude>` | Latitude en degrés × 100 000, parfois avec décimales | `4620100` |
| `longitude` | VARCHAR | `<pdv longitude>` | Longitude en degrés × 100 000 | `519800` |
| `cp` | VARCHAR | `<pdv cp>` | Code postal | `01000` |
| `pop` | VARCHAR | `<pdv pop>` | `R` route, `A` autoroute, `N` (une station) | `R` |
| `adresse` | VARCHAR | `<adresse>` | Adresse, casse d'origine | `596 AVENUE DE TREVOUX` |
| `ville` | VARCHAR | `<ville>` | Ville, casse d'origine | `SAINT-DENIS-LèS-BOURG` |
| `_source_year` … `_loaded_at` | | | Colonnes techniques, comme dans `raw.prix` | |

**À savoir**

- **Toutes les stations du fichier n'ont pas de prix** : en 2026, 9 774 stations sur 14 793 ont au moins un prix. 4 978 n'ont qu'une balise `<prix/>` vide, 41 aucune balise `<prix>`.
- **Coordonnées aberrantes, seulement sur des stations sans prix** : 69 stations sans coordonnées, et d'autres à `0`, avec latitude et longitude inversées, ou à La Réunion. Les stations avec prix sont toutes en France métropolitaine (vérifié par un test).
- **Adresses** : 244 adresses de 2026 ont des espaces en fin de texte.
- **Villes** : environ la moitié en majuscules, avec parfois les accents restés en minuscules (`TOURNON-SUR-RHôNE`).

## `staging.stg_roulez_eco__prix`

Relevés de prix typés, un par station, carburant et instant de relevé.

- **Source** : `raw.prix`, sans les balises `<prix/>` vides.
- **Relevés en conflit** : quand deux relevés ont le même instant et deux prix différents (2 cas en 2025 et 2026), le plus élevé est gardé.
- **Volume** : 9 465 583 lignes, soit les relevés de la source moins les 2 relevés en conflit écartés.

| Colonne | Type | Source | Description | Exemple |
|---|---|---|---|---|
| `station_id` | INTEGER | `pdv_id` | Identifiant de la station | `1000001` |
| `carburant_id` | SMALLINT | `prix_id` | `1` Gazole, `2` SP95, `3` E85, `4` GPLc, `5` E10, `6` SP98 | `1` |
| `carburant` | VARCHAR | `prix_nom` | Nom du carburant | `Gazole` |
| `maj_at` | TIMESTAMP WITH TIME ZONE | `maj` | Instant du relevé, `maj` étant lu en heure de Paris | `2026-09-25 00:42:00+02` |
| `prix_litre` | DECIMAL(8,3) | `valeur` | Prix en euros par litre | `2.424` |
| `_source_year` … `_loaded_at` | | | Repris de `raw` | |

## `staging.stg_roulez_eco__stations`

Stations typées, une ligne par station et par fichier annuel : une station listée en 2025 et en 2026 a deux lignes. Le mart des stations choisit la version la plus récente parmi les années avec prix.

| Colonne | Type | Source | Description | Exemple |
|---|---|---|---|---|
| `station_id` | INTEGER | `pdv_id` | Identifiant de la station | `1000001` |
| `adresse` | VARCHAR | `adresse` | Sans espaces au début ni à la fin, casse d'origine | `596 AVENUE DE TREVOUX` |
| `ville` | VARCHAR | `ville` | Sans espaces au début ni à la fin, casse d'origine | `SAINT-DENIS-LèS-BOURG` |
| `code_postal` | VARCHAR | `cp` | Code postal | `01000` |
| `latitude` | DOUBLE | `latitude` | En degrés ; NULL si absente | `46.201` |
| `longitude` | DOUBLE | `longitude` | En degrés ; NULL si absente | `5.198` |
| `est_autoroute` | BOOLEAN | `pop` | Vrai si `pop = 'A'` ; `N` compte comme route | `false` |
| `_source_year` … `_loaded_at` | | | Repris de `raw` | |

**À savoir** : le staging garde toutes les stations, avec ou sans prix, et leurs coordonnées telles quelles. Seules les stations avec prix sont retenues dans les marts.

## `marts.mart_changements_prix`

Historique des changements de prix : un relevé n'est gardé que si son prix diffère du relevé précédent de la même station pour le même carburant.

- **Grain** : une station, un carburant, un instant de changement.
- **Source** : `stg_roulez_eco__prix`.
- **Volume** : 5 222 646 lignes sur 9 465 583 relevés (45 % des relevés répètent le prix précédent), dont 37 039 premiers relevés, 2 748 854 hausses et 2 436 753 baisses.

| Colonne | Type | Description | Exemple |
|---|---|---|---|
| `station_id` | INTEGER | Identifiant de la station | `1000001` |
| `carburant_id` | SMALLINT | Identifiant du carburant | `1` |
| `carburant` | VARCHAR | Nom du carburant | `Gazole` |
| `maj_at` | TIMESTAMP WITH TIME ZONE | Instant du changement | `2026-09-25 00:42:00+02` |
| `prix_litre` | DECIMAL(8,3) | Nouveau prix, en euros par litre | `2.424` |
| `prix_precedent` | DECIMAL(8,3) | Prix d'avant le changement ; NULL pour le premier relevé | `2.451` |
| `variation` | DECIMAL | `prix_litre - prix_precedent` ; NULL pour le premier relevé | `-0.027` |
| `est_premier_releve` | BOOLEAN | Premier relevé connu du couple | `false` |
| `est_prix_suspect` | BOOLEAN | Prix d'E85 ou de GPLc au niveau de l'essence | `false` |
| `changement_precedent_at` | TIMESTAMP WITH TIME ZONE | Instant du changement précédent ; NULL pour le premier relevé | `2026-09-22 00:41:00+02` |

**À savoir**

- Le premier relevé d'un couple marque le début de l'historique chargé (janvier 2025 pour la plupart des couples, plus tard pour une station ou un carburant apparu ensuite), pas forcément un vrai changement : `est_premier_releve` permet de l'exclure d'un calcul de variations.
- La variation médiane est de 1,3 centime. Les plus fortes (jusqu'à 1,70 €) viennent surtout des prix suspects, qui font des allers-retours entre prix réel et prix saisi par erreur : 515 changements sont marqués `est_prix_suspect`.

## `marts.mart_stations`

Stations ayant publié au moins un prix, dans leur version la plus récente parmi les années où elles ont des prix.

- **Grain** : une station.
- **Source** : `stg_roulez_eco__stations` et `stg_roulez_eco__prix`.
- **Volume** : 10 112 stations, dont 9 774 dans leur version 2026 et 338 dans leur version 2025.

| Colonne | Type | Description | Exemple |
|---|---|---|---|
| `station_id` | INTEGER | Identifiant de la station | `1000001` |
| `adresse` | VARCHAR | Adresse, casse d'origine | `596 AVENUE DE TREVOUX` |
| `ville` | VARCHAR | Ville, casse d'origine | `SAINT-DENIS-LèS-BOURG` |
| `code_postal` | VARCHAR | Code postal | `01000` |
| `latitude` | DOUBLE | En degrés | `46.201` |
| `longitude` | DOUBLE | En degrés | `5.198` |
| `est_autoroute` | BOOLEAN | Station d'autoroute | `false` |
| `premier_releve_at` | TIMESTAMP WITH TIME ZONE | Premier relevé de prix chargé, tous carburants | `2025-01-02 00:37:00+01` |
| `dernier_releve_at` | TIMESTAMP WITH TIME ZONE | Dernier relevé de prix, tous carburants | `2026-09-25 00:42:00+02` |
| `nombre_carburants` | BIGINT | Carburants ayant eu au moins un prix | `5` |
| `nombre_releves` | BIGINT | Relevés de prix, répétitions comprises | `2052` |
| `annee_version` | SMALLINT | Année du fichier d'où viennent l'adresse et les coordonnées | `2026` |

**À savoir**

- Les 338 stations en version 2025 n'ont plus publié de prix en 2026 : elles ont probablement fermé. Elles restent dans le mart, avec un `dernier_releve_at` ancien.
- Une version sans prix n'est jamais retenue : ses coordonnées peuvent être fausses (`0`, latitude et longitude inversées…).

## `marts.mart_prix_actuels`

Dernier prix connu de chaque station pour chaque carburant, avec son âge.

- **Grain** : une station, un carburant.
- **Source** : `stg_roulez_eco__prix`.
- **Volume** : 37 039 prix.

| Colonne | Type | Description | Exemple |
|---|---|---|---|
| `station_id` | INTEGER | Identifiant de la station | `1000001` |
| `carburant_id` | SMALLINT | Identifiant du carburant | `1` |
| `carburant` | VARCHAR | Nom du carburant | `Gazole` |
| `prix_litre` | DECIMAL(8,3) | Dernier prix connu, en euros par litre | `2.424` |
| `maj_at` | TIMESTAMP WITH TIME ZONE | Instant du dernier relevé de ce prix | `2026-09-25 00:42:00+02` |
| `est_prix_suspect` | BOOLEAN | Prix d'E85 ou de GPLc au niveau de l'essence | `false` |
| `nombre_jours_depuis_maj` | BIGINT | Jours calendaires, à l'heure de Paris, entre `maj_at` et `reference_at` | `2` |
| `reference_at` | TIMESTAMP WITH TIME ZONE | Dernier relevé de toutes les données | `2026-09-27 23:59:00+02` |

| Âge du prix | Prix | Part |
|---|---|---|
| 1 jour ou moins | 8 763 | 24 % |
| 7 jours ou moins | 26 317 | 71 % |
| 30 jours ou moins | 33 484 | 90 % |
| Plus de 180 jours | 1 846 | 5 % |

**À savoir**

- **Tous les derniers prix sont gardés**, même anciens : le portfolio décide de leur affichage (grisés au-delà de 7 jours).
- **L'âge est compté depuis le dernier relevé des données**, pas depuis l'heure d'exécution : relancer dbt sur les mêmes données donne le même résultat. Les jours sont comptés à l'heure de Paris, quel que soit le fuseau de la machine. Un test garantit qu'aucun relevé n'est postérieur au chargement, sinon `reference_at` serait faussé.
- **66 prix suspects** (54 en E85, 12 en GPLc), soit 0,2 % : ils ne doivent pas être affichés comme les moins chers. Seuils : 1,50 € pour l'E85, 1,80 € pour le GPLc (variables `prix_max_plausible_e85` et `prix_max_plausible_gplc` de `dbt_project.yml`).
- **Les ruptures de stock ne sont pas chargées** : un carburant en rupture garde son dernier prix.

## Fichiers exportés

Écrits par `export.py` dans `exports/`, pour le portfolio. Les deux fichiers sont entièrement réécrits à chaque exécution, de façon atomique.

### `prix_actuels.json`

Les stations de `mart_stations` et leurs prix de `mart_prix_actuels`, dans un format compact : chaque station et chaque prix est un tableau, et l'ordre des valeurs n'est donné qu'une fois. 10 112 stations, 37 039 prix, 2,2 Mo (0,5 Mo compressé en gzip).

```json
{
  "reference_at": "2026-09-27T21:59:00Z",
  "colonnes_station": ["id", "latitude", "longitude", "adresse", "ville", "code_postal", "autoroute", "prix"],
  "colonnes_prix": ["carburant_id", "prix", "maj", "age_jours", "suspect"],
  "stations": [
    [1000001, 46.201, 5.198, "596 AVENUE DE TREVOUX", "SAINT-DENIS-LèS-BOURG", "01000", false,
      [[1, 2.424, "2026-09-24T22:42Z", 2, false], [2, 2.225, "2026-09-24T22:42Z", 2, false], ...]]
  ]
}
```

| Valeur | Source | Description |
|---|---|---|
| `reference_at` | `mart_prix_actuels.reference_at` | Dernier relevé des données, en UTC |
| `id` | `mart_stations.station_id` | Identifiant de la station |
| `latitude`, `longitude` | `mart_stations` | En degrés, arrondies à 5 décimales (environ 1 m) |
| `adresse`, `ville`, `code_postal` | `mart_stations` | Casse d'origine |
| `autoroute` | `mart_stations.est_autoroute` | Station d'autoroute |
| `carburant_id` | `mart_prix_actuels` | `1` Gazole, `2` SP95, `3` E85, `4` GPLc, `5` E10, `6` SP98 (table dans `metadata.json`) |
| `prix` | `mart_prix_actuels.prix_litre` | Euros par litre |
| `maj` | `mart_prix_actuels.maj_at` | Instant du dernier relevé, en UTC, à la minute |
| `age_jours` | `mart_prix_actuels.nombre_jours_depuis_maj` | Jours calendaires, à l'heure de Paris, entre `maj` et `reference_at` |
| `suspect` | `mart_prix_actuels.est_prix_suspect` | Prix d'E85 ou de GPLc au niveau de l'essence |

### `metadata.json`

| Clé | Contenu |
|---|---|
| `genere_le` | Date et heure de l'export, en UTC |
| `reference_at` | Dernier relevé des données, en UTC |
| `fichiers_source` | Pour chaque année : ZIP chargé, empreinte sha256, date du chargement |
| `volumes` | Stations, prix actuels, prix de 7 jours ou moins, prix suspects, changements de prix |
| `source` | Producteur, URL et licence |
| `carburants` | Correspondance entre `carburant_id` et nom |
| `regles_de_lecture` | Règles d'affichage pour le portfolio : instants en UTC, âge compté depuis `reference_at`, prix grisés au-delà de 7 jours, prix suspects, couverture métropole et Corse, casse des villes |
| `derniere_execution_dbt` | Commande, sélection, date, durée, modèles et tests par statut, lus dans `dbt/target/run_results.json` |
