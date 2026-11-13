-- Règle du mart des prix médians : chaque station compte au plus une fois par jour
-- et par carburant. Le nombre de stations d'un jour ne peut donc pas dépasser le
-- nombre de stations qui ont un relevé de ce carburant dans la fenêtre des prix en
-- vigueur ; il lui est égal quand aucun prix n'est suspect. Un recouvrement de
-- deux périodes le jour d'un changement de prix compterait la station deux fois.
with jours_releves as (

    select distinct
        station_id,
        carburant_id,
        cast(timezone('Europe/Paris', maj_at) as date) as jour
    from {{ ref('stg_roulez_eco__prix') }}

),

stations_possibles as (

    select m.jour, m.carburant_id, count(distinct r.station_id) as stations_possibles
    from {{ ref('mart_prix_medians_quotidiens') }} as m
    join jours_releves as r
      on r.carburant_id = m.carburant_id
     and r.jour between m.jour - {{ var('jours_prix_en_vigueur') }} and m.jour
    group by m.jour, m.carburant_id

)

select m.jour, m.carburant, m.nombre_stations, s.stations_possibles
from {{ ref('mart_prix_medians_quotidiens') }} as m
join stations_possibles as s using (jour, carburant_id)
where m.nombre_stations > s.stations_possibles
