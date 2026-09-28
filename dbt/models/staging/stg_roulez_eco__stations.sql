-- Stations typées, une ligne par station et par fichier annuel.
--
-- Une station apparaît dans chaque fichier annuel où elle est listée : la
-- version la plus récente sera choisie dans le mart des stations.
-- Nettoyage :
--   - coordonnées converties en degrés (la source les donne en degrés × 100 000) ;
--   - adresse et ville débarrassées de leurs espaces en trop, casse d'origine gardée ;
--   - pop réduit à est_autoroute : la valeur N (une seule station) compte comme route.

with stations as (

    select *
    from {{ source('roulez_eco', 'stations') }}

)

select
    cast(pdv_id as integer)                             as station_id,
    trim(adresse)                                       as adresse,
    trim(ville)                                         as ville,
    cp                                                  as code_postal,
    cast(nullif(latitude, '') as double) / 100000       as latitude,
    cast(nullif(longitude, '') as double) / 100000      as longitude,
    pop = 'A'                                           as est_autoroute,
    _source_year,
    _source_file,
    _source_sha256,
    _loaded_at
from stations
