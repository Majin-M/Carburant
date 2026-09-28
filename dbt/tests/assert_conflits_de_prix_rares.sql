-- Constat d'exploration : un seul couple station × carburant par année a deux
-- relevés au même maj avec deux prix différents (2 cas pour 2025 et 2026).
-- Le staging garde le plus élevé ; au-delà de 10 cas, la règle est à revoir.
select count(*) - count(distinct (pdv_id, prix_id, maj)) as releves_en_conflit
from {{ source('roulez_eco', 'prix') }}
where prix_id is not null
having count(*) - count(distinct (pdv_id, prix_id, maj)) > 10
