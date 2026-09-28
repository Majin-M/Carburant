-- Chaque couple station × carburant du staging a exactement un premier relevé dans
-- le mart des changements : aucun couple perdu, aucun historique coupé en deux.
with couples_staging as (
    select distinct station_id, carburant_id
    from {{ ref('stg_roulez_eco__prix') }}
),

premiers as (
    select station_id, carburant_id, count(*) as premiers_releves
    from {{ ref('mart_changements_prix') }}
    where est_premier_releve
    group by station_id, carburant_id
)

select c.station_id, c.carburant_id, coalesce(p.premiers_releves, 0) as premiers_releves
from couples_staging as c
full outer join premiers as p using (station_id, carburant_id)
where coalesce(p.premiers_releves, 0) <> 1
   or c.station_id is null
