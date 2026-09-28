-- Constat d'exploration : les stations avec prix sont toutes en France métropolitaine,
-- Corse comprise. Le mart des stations, lu par le portfolio pour la recherche
-- « autour de moi », ne doit contenir aucune coordonnée aberrante.
select station_id, code_postal, latitude, longitude
from {{ ref('mart_stations') }}
where latitude not between 41 and 51.5
   or longitude not between -5.5 and 10
