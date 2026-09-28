-- Constat d'exploration : le fichier annuel d'une année ne contient que des relevés
-- de cette année (du 1er janvier 00:00 au 31 décembre 23:59 pour 2025).
select pdv_id, prix_id, maj, _source_year
from {{ source('roulez_eco', 'prix') }}
where prix_id is not null
  and year(cast(maj as timestamp)) <> _source_year
