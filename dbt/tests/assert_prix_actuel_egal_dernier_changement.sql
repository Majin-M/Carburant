-- Cohérence entre marts : le prix actuel d'un couple est celui de son dernier
-- changement. Sinon, l'un des deux marts ordonne mal les relevés.
with derniers_changements as (
    select station_id, carburant_id, prix_litre
    from {{ ref('mart_changements_prix') }}
    qualify row_number() over (partition by station_id, carburant_id order by maj_at desc) = 1
)

select a.station_id, a.carburant_id, a.prix_litre as prix_actuel, d.prix_litre as prix_dernier_changement
from {{ ref('mart_prix_actuels') }} as a
left join derniers_changements as d using (station_id, carburant_id)
where d.prix_litre is null or a.prix_litre <> d.prix_litre
