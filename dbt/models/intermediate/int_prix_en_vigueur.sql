-- Prix en vigueur de chaque station, pour chaque carburant et chaque jour.
--
-- Un prix est en vigueur un jour donné s'il est le dernier relevé de la station
-- à la fin de ce jour, en heure de Paris, et si ce relevé a au plus
-- jours_prix_en_vigueur jours : la règle de la recherche du portfolio, qui grise
-- les prix plus anciens. Une ligne par station, carburant et jour, quel que soit
-- le nombre de relevés de la journée. Les prix suspects sont gardés et marqués.
--
-- Sert aux prix médians quotidiens et aux écarts entre autoroute et route.

with releves_du_jour as (

    -- Dernier relevé de chaque station, pour chaque carburant et chaque jour.
    select
        station_id,
        carburant_id,
        carburant,
        cast(timezone('Europe/Paris', maj_at) as date) as jour,
        arg_max(prix_litre, maj_at)                    as prix_litre
    from {{ ref('stg_roulez_eco__prix') }}
    group by station_id, carburant_id, carburant, jour

),

bornes as (

    select max(jour) as dernier_jour
    from releves_du_jour

),

periodes as (

    -- Un relevé reste en vigueur jusqu'à la veille du relevé suivant, au plus
    -- jours_prix_en_vigueur jours, et jamais après le dernier jour des données.
    select
        releves_du_jour.*,
        least(
            coalesce(
                lead(jour) over (partition by station_id, carburant_id order by jour) - 1,
                bornes.dernier_jour
            ),
            jour + {{ var('jours_prix_en_vigueur') }},
            bornes.dernier_jour
        ) as dernier_jour_en_vigueur
    from releves_du_jour
    cross join bornes

)

select
    station_id,
    carburant_id,
    carburant,
    cast(unnest(generate_series(jour, dernier_jour_en_vigueur, interval 1 day)) as date) as jour,
    prix_litre,
    jour                                                                                 as releve_le,
    {{ est_prix_suspect('carburant_id', 'prix_litre') }}                                  as est_prix_suspect
from periodes
