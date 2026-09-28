-- L'âge d'un prix est compté depuis le dernier relevé des données : il ne peut pas
-- être négatif. Sinon, la date de référence est mal calculée.
select station_id, carburant_id, maj_at, reference_at, nombre_jours_depuis_maj
from {{ ref('mart_prix_actuels') }}
where nombre_jours_depuis_maj < 0
