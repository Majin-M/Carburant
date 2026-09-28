-- Relevés de prix typés : un prix par station, carburant et instant de relevé.
--
-- Nettoyage :
--   - les balises <prix/> vides (stations sans prix dans l'année) sont écartées ;
--   - maj est lu en heure de Paris (constat d'exploration) et stocké avec fuseau,
--     pour que l'ordre reste juste lors du passage à l'heure d'hiver ;
--   - prix_litre est en DECIMAL(8, 3) et non (5, 3) : un prix en millièmes (1638,
--     format des anciens fichiers) doit passer la conversion pour que le test
--     assert_prix_entre_0_30_et_4_euros le signale, au lieu de faire planter la vue ;
--   - quand deux relevés ont le même instant et deux prix différents (un seul cas
--     par année), on garde le plus élevé : mieux vaut ne pas afficher comme
--     « moins chère » une station sur la foi d'un prix douteux.

with releves as (

    select *
    from {{ source('roulez_eco', 'prix') }}
    where prix_id is not null

)

select
    cast(pdv_id as integer)                             as station_id,
    cast(prix_id as smallint)                           as carburant_id,
    prix_nom                                            as carburant,
    timezone('Europe/Paris', cast(maj as timestamp))    as maj_at,
    cast(valeur as decimal(8, 3))                       as prix_litre,
    _source_year,
    _source_file,
    _source_sha256,
    _loaded_at
from releves
qualify row_number() over (
    partition by pdv_id, prix_id, maj
    order by cast(valeur as decimal(8, 3)) desc
) = 1
