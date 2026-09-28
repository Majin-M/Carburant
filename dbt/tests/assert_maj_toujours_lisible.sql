-- Constat d'exploration : dans les fichiers 2025 et 2026, chaque maj d'un relevé
-- est au format ISO AAAA-MM-JJTHH:MM:SS. Un maj illisible ferait échouer le staging.
select pdv_id, prix_id, maj, _source_year
from {{ source('roulez_eco', 'prix') }}
where prix_id is not null
  and try_cast(maj as timestamp) is null
