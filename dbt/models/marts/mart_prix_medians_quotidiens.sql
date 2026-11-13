-- Prix médian de chaque carburant, jour par jour, sur les prix en vigueur.
--
-- Un prix est en vigueur un jour donné s'il est le dernier relevé de la station
-- à la fin de ce jour, en heure de Paris, et si ce relevé a au plus
-- jours_prix_en_vigueur jours : la règle de la recherche du portfolio, qui grise
-- les prix plus anciens. Chaque station compte une fois par jour, quel que soit
-- son nombre de relevés : une médiane des relevés surpondérerait les stations qui
-- relèvent plusieurs fois par jour. Les prix suspects sont écartés.
--
-- Les premiers jours de l'historique n'ont pas encore les relevés des jours
-- précédents : la série commence une fois la fenêtre complète.

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

    select min(jour) as premier_jour, max(jour) as dernier_jour
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

),

prix_en_vigueur as (

    select
        carburant_id,
        carburant,
        cast(unnest(generate_series(jour, dernier_jour_en_vigueur, interval 1 day)) as date) as jour,
        prix_litre
    from periodes
    where not {{ est_prix_suspect('carburant_id', 'prix_litre') }}

)

select
    prix_en_vigueur.jour,
    carburant_id,
    carburant,
    median(prix_litre)  as prix_median,
    count(*)            as nombre_stations
from prix_en_vigueur
cross join bornes
where prix_en_vigueur.jour >= bornes.premier_jour + {{ var('jours_prix_en_vigueur') }}
group by prix_en_vigueur.jour, carburant_id, carburant
