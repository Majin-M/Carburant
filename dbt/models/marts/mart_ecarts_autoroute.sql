-- Écart de prix entre stations d'autoroute et de route, à la même date et dans
-- le même département, pour chaque carburant.
--
-- Comparer les médianes nationales mélangerait l'effet autoroute et l'effet
-- géographique : les autoroutes traversent surtout des départements déjà chers.
-- Chaque ligne compare donc, un jour donné et dans un département, le prix médian
-- en vigueur des stations d'autoroute à celui des stations de route. Seuls les
-- jours et départements qui ont au moins une station de chaque type sont gardés.
-- Prix en vigueur et prix suspects écartés : comme mart_prix_medians_quotidiens.

with prix_en_vigueur as (

    select
        p.jour,
        p.carburant_id,
        p.carburant,
        p.prix_litre,
        s.est_autoroute,
        -- Deux premiers caractères du code postal : 20 pour toute la Corse.
        left(s.code_postal, 2) as departement
    from {{ ref('int_prix_en_vigueur') }} as p
    join {{ ref('mart_stations') }} as s using (station_id)
    where not p.est_prix_suspect

),

debut as (

    select min(releve_le) + {{ var('jours_prix_en_vigueur') }} as premier_jour_complet
    from {{ ref('int_prix_en_vigueur') }}

),

par_type as (

    select
        jour,
        departement,
        carburant_id,
        carburant,
        median(prix_litre) filter (where est_autoroute)     as prix_median_autoroute,
        median(prix_litre) filter (where not est_autoroute) as prix_median_route,
        count(*) filter (where est_autoroute)               as nombre_stations_autoroute,
        count(*) filter (where not est_autoroute)           as nombre_stations_route
    from prix_en_vigueur
    cross join debut
    where jour >= debut.premier_jour_complet
    group by jour, departement, carburant_id, carburant

)

select
    *,
    prix_median_autoroute - prix_median_route as ecart
from par_type
where nombre_stations_autoroute > 0
  and nombre_stations_route > 0
