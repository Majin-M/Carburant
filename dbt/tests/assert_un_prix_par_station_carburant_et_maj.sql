-- Grain du staging : un seul prix par station, carburant et instant de relevé,
-- une fois les deux relevés en conflit départagés.
select station_id, carburant_id, maj_at, count(*) as prix
from {{ ref('stg_roulez_eco__prix') }}
group by station_id, carburant_id, maj_at
having count(*) > 1
