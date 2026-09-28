-- Un relevé ne peut pas être postérieur au chargement du fichier qui le contient.
-- Sans ce test, un seul maj saisi dans le futur (le 31/12 au lieu du 31/01) resterait
-- dans la bonne année, passerait tous les autres tests, et décalerait reference_at :
-- la date des données et l'âge de tous les prix actuels seraient faux.
select station_id, carburant, maj_at, _loaded_at, _source_file
from {{ ref('stg_roulez_eco__prix') }}
where maj_at > _loaded_at
