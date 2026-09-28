-- Historique des changements de prix : un relevé n'est gardé que si son prix
-- diffère du relevé précédent de la même station pour le même carburant.
--
-- Constat d'exploration : 47 % des relevés répètent le prix précédent. Le premier
-- relevé de chaque couple station × carburant est gardé (lag y vaut NULL) : il
-- marque le début de l'historique connu, pas forcément un vrai changement.
-- L'ordre suit maj_at, avec fuseau : il reste juste lors du passage à l'heure d'hiver.

with releves as (

    select station_id, carburant_id, carburant, maj_at, prix_litre
    from {{ ref('stg_roulez_eco__prix') }}

),

changements as (

    select
        *,
        lag(prix_litre) over releves_du_couple as prix_precedent
    from releves
    window releves_du_couple as (partition by station_id, carburant_id order by maj_at)
    -- Le relevé précédent a forcément le prix du dernier changement : prix_precedent
    -- est donc aussi le prix d'avant le changement.
    qualify prix_litre is distinct from lag(prix_litre) over releves_du_couple

)

select
    station_id,
    carburant_id,
    carburant,
    maj_at,
    prix_litre,
    prix_precedent,
    prix_litre - prix_precedent                                             as variation,
    prix_precedent is null                                                  as est_premier_releve,
    {{ est_prix_suspect('carburant_id', 'prix_litre') }}                     as est_prix_suspect,
    lag(maj_at) over (partition by station_id, carburant_id order by maj_at) as changement_precedent_at
from changements
