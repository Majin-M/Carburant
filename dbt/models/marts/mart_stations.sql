-- Stations en activité : une ligne par station ayant au moins un prix.
--
-- Constat d'exploration : un tiers des stations des fichiers annuels n'ont aucun
-- prix, et les coordonnées aberrantes ne touchent que celles-là. Elles sont écartées.
-- Une station listée plusieurs années prend sa version la plus récente parmi les
-- années où elle a publié des prix : une version sans prix peut avoir des
-- coordonnées fausses.

with prix as (

    select station_id, carburant_id, maj_at, _source_year
    from {{ ref('stg_roulez_eco__prix') }}

),

annees_avec_prix as (

    select distinct station_id, _source_year
    from prix

),

derniere_version as (

    select stations.*
    from {{ ref('stg_roulez_eco__stations') }} as stations
    join annees_avec_prix using (station_id, _source_year)
    qualify row_number() over (partition by station_id order by _source_year desc) = 1

),

activite as (

    select
        station_id,
        min(maj_at)                    as premier_releve_at,
        max(maj_at)                    as dernier_releve_at,
        count(distinct carburant_id)   as nombre_carburants,
        count(*)                       as nombre_releves
    from prix
    group by station_id

)

select
    derniere_version.station_id,
    derniere_version.adresse,
    derniere_version.ville,
    derniere_version.code_postal,
    derniere_version.latitude,
    derniere_version.longitude,
    derniere_version.est_autoroute,
    activite.premier_releve_at,
    activite.dernier_releve_at,
    activite.nombre_carburants,
    activite.nombre_releves,
    derniere_version._source_year  as annee_version
from derniere_version
join activite using (station_id)
