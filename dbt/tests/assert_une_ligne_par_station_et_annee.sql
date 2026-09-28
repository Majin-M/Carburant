-- Constat d'exploration : chaque station n'apparaît qu'une fois par fichier annuel.
select station_id, _source_year, count(*) as lignes
from {{ ref('stg_roulez_eco__stations') }}
group by station_id, _source_year
having count(*) > 1
