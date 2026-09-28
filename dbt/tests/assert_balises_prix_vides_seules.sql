-- Constat d'exploration : une station sans aucun prix dans l'année porte une seule
-- balise <prix/> vide, jamais à côté d'un vrai prix. Si ce n'est plus vrai, une
-- balise vide peut signaler autre chose (prix supprimé ?) et le filtre du staging
-- est à revoir.
select pdv_id, _source_year,
       count(*) filter (prix_id is null)     as balises_vides,
       count(*) filter (prix_id is not null) as vrais_prix
from {{ source('roulez_eco', 'prix') }}
group by pdv_id, _source_year
having count(*) filter (prix_id is null) > 0
   and (count(*) filter (prix_id is null) > 1 or count(*) filter (prix_id is not null) > 0)
