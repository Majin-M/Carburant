-- Vrai si le prix est probablement une erreur de saisie : un prix d'E85 (3) ou de
-- GPLc (4) au niveau de l'essence. Les seuils sont les variables du dbt_project.yml.
{% macro est_prix_suspect(carburant_id, prix_litre) -%}
    case {{ carburant_id }}
        when 3 then {{ prix_litre }} > {{ var('prix_max_plausible_e85') }}
        when 4 then {{ prix_litre }} > {{ var('prix_max_plausible_gplc') }}
        else false
    end
{%- endmacro %}
