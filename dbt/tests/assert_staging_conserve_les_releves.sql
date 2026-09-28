-- Le staging n'écarte que les balises vides et les relevés en conflit : il doit
-- garder exactement un relevé par station, carburant et maj de la source.
with source as (
    select count(distinct (pdv_id, prix_id, maj)) as releves
    from {{ source('roulez_eco', 'prix') }}
    where prix_id is not null
),

staging as (
    select count(*) as releves
    from {{ ref('stg_roulez_eco__prix') }}
)

select source.releves as releves_source, staging.releves as releves_staging
from source, staging
where source.releves <> staging.releves
