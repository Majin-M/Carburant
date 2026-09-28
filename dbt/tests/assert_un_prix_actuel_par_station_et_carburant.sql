-- Grain du mart des prix actuels : un seul prix par station et par carburant.
select station_id, carburant_id, count(*) as prix
from {{ ref('mart_prix_actuels') }}
group by station_id, carburant_id
having count(*) > 1
