-- Constat d'exploration : les coordonnées aberrantes (0, latitude et longitude
-- inversées, La Réunion…) ne concernent que des stations sans prix. Toute station
-- avec au moins un prix doit être placée en France métropolitaine, Corse comprise :
-- sinon, la recherche « autour de moi » la placerait au mauvais endroit.
with stations_avec_prix as (
    select distinct station_id, _source_year
    from {{ ref('stg_roulez_eco__prix') }}
)

select s.station_id, s._source_year, s.code_postal, s.latitude, s.longitude
from {{ ref('stg_roulez_eco__stations') }} as s
join stations_avec_prix using (station_id, _source_year)
where s.latitude is null
   or s.longitude is null
   or s.latitude not between 41 and 51.5
   or s.longitude not between -5.5 and 10
