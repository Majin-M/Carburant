-- Définition du mart des changements : hors premier relevé, chaque ligne a un prix
-- différent du précédent. Une variation nulle signalerait un relevé répété oublié.
select station_id, carburant_id, maj_at, prix_precedent, prix_litre
from {{ ref('mart_changements_prix') }}
where not est_premier_releve
  and (prix_precedent is null or prix_litre = prix_precedent)
