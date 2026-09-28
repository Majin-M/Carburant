-- Dernier prix connu de chaque station pour chaque carburant, avec son âge.
--
-- Tous les derniers prix sont gardés, même anciens : c'est au portfolio de
-- décider comment afficher un prix vieux de plusieurs semaines (grisé au-delà
-- de 7 jours). Les prix suspects (E85 ou GPLc au niveau de l'essence) sont
-- gardés et marqués, pour que le portfolio puisse les écarter. L'âge est compté depuis le dernier relevé des données, pas depuis
-- l'heure d'exécution : relancer dbt sur les mêmes données donne le même résultat.

with derniers_prix as (

    select station_id, carburant_id, carburant, maj_at, prix_litre
    from {{ ref('stg_roulez_eco__prix') }}
    qualify row_number() over (partition by station_id, carburant_id order by maj_at desc) = 1

),

reference as (

    select max(maj_at) as reference_at
    from {{ ref('stg_roulez_eco__prix') }}

)

select
    derniers_prix.station_id,
    derniers_prix.carburant_id,
    derniers_prix.carburant,
    derniers_prix.prix_litre,
    derniers_prix.maj_at,
    {{ est_prix_suspect('derniers_prix.carburant_id', 'derniers_prix.prix_litre') }} as est_prix_suspect,
    -- Jours comptés en heure de Paris, explicitement : sur un horodatage avec fuseau,
    -- date_diff suit le fuseau de la session, et une machine en UTC (GitHub Actions)
    -- donnerait un autre âge à plus de 5 000 prix.
    date_diff(
        'day',
        cast(timezone('Europe/Paris', derniers_prix.maj_at) as date),
        cast(timezone('Europe/Paris', reference.reference_at) as date)
    )                                                                 as nombre_jours_depuis_maj,
    reference.reference_at
from derniers_prix
cross join reference
