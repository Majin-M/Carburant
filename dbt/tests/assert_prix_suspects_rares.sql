-- Constat d'exploration : quelques stations saisissent pour l'E85 ou le GPLc un
-- prix au niveau de l'essence (E85 entre 1,6 et 2,3 € au lieu d'environ 0,85 €).
-- Ces prix sont marqués est_prix_suspect. Ils représentent 0,2 % des prix actuels :
-- au-delà de 1 %, les seuils sont probablement à revoir, ou la source a changé.
{{ config(severity = 'warn') }}

select
    count(*) filter (est_prix_suspect)              as prix_suspects,
    count(*)                                        as prix_actuels
from {{ ref('mart_prix_actuels') }}
having count(*) filter (est_prix_suspect) > 0.01 * count(*)
