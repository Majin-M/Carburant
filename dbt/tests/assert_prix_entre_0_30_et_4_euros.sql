-- Constat d'exploration : en 2025 et 2026, tous les prix sont entre 0,383 € (E85)
-- et 3,000 € le litre. Un prix hors de 0,30 € à 4 € est une erreur de saisie ou
-- un changement d'unité : les fichiers 2015 et 2021 donnent les prix en millièmes (1141).
select station_id, carburant, maj_at, prix_litre
from {{ ref('stg_roulez_eco__prix') }}
where prix_litre not between 0.30 and 4
