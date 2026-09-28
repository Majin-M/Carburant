-- Constat d'exploration : maj est en heure de Paris. La nuit du passage à l'heure
-- d'été (dernier dimanche de mars), l'heure de 2 h à 3 h n'existe pas. Un relevé
-- dans ce créneau contredirait le constat, ou serait converti à une heure fausse.
select pdv_id, prix_id, maj, _source_year
from {{ source('roulez_eco', 'prix') }}
where prix_id is not null
  and month(cast(maj as timestamp)) = 3
  and dayofweek(cast(maj as timestamp)) = 0        -- dimanche
  and day(cast(maj as timestamp)) >= 25            -- dernier dimanche du mois
  and hour(cast(maj as timestamp)) = 2
