-- Prix médian de chaque carburant, jour par jour, sur les prix en vigueur
-- (int_prix_en_vigueur : dernier relevé de chaque station, de
-- jours_prix_en_vigueur jours au plus). Chaque station compte une fois par jour,
-- quel que soit son nombre de relevés : une médiane des relevés surpondérerait
-- les stations qui relèvent plusieurs fois par jour. Les prix suspects sont écartés.
--
-- Les premiers jours de l'historique n'ont pas encore les relevés des jours
-- précédents : la série commence une fois la fenêtre complète.

with prix_en_vigueur as (

    select *
    from {{ ref('int_prix_en_vigueur') }}
    where not est_prix_suspect

),

debut as (

    select min(releve_le) + {{ var('jours_prix_en_vigueur') }} as premier_jour_complet
    from {{ ref('int_prix_en_vigueur') }}

)

select
    jour,
    carburant_id,
    carburant,
    median(prix_litre)  as prix_median,
    count(*)            as nombre_stations
from prix_en_vigueur
cross join debut
where jour >= debut.premier_jour_complet
group by jour, carburant_id, carburant
