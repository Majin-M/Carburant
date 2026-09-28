-- Par défaut, dbt préfixe le schéma personnalisé par celui du profil (main_staging).
-- On veut exactement les schémas des conventions : staging et marts.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
