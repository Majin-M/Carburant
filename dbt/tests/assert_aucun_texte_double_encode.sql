-- Constat d'exploration : la source écrit quelques adresses encodées deux fois
-- (« 77 Avenue Ãdouard Depreux » pour « Édouard »). Le staging les répare ; aucune
-- adresse ni ville ne doit garder la trace d'un double encodage, « Ã » suivi d'un
-- caractère entre U+0080 et U+00BF, sinon le portfolio l'affiche.
select station_id, _source_year, adresse, ville
from {{ ref('stg_roulez_eco__stations') }}
where regexp_matches(adresse, 'Ã[\x{80}-\x{BF}]')
   or regexp_matches(ville, 'Ã[\x{80}-\x{BF}]')
