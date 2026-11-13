-- Répare un texte encodé deux fois, tel que la source l'écrit pour quelques adresses :
-- « É » y est écrit &#xC3;&#x89;, soit ses deux octets UTF-8 lus comme deux caractères
-- (« Ã » puis U+0089). Le texte est alors refait octet par octet et relu en UTF-8.
-- Il reste tel quel s'il ne contient pas « Ã », s'il a un caractère au-delà de U+00FF
-- (il ne peut pas venir d'octets) ou si la relecture en UTF-8 échoue (vrai « Ã »).
{% macro reparer_double_encodage(texte) -%}
    case
        when {{ texte }} like '%Ã%'
         and list_bool_and(list_transform(string_split({{ texte }}, ''), c -> unicode(c) < 256))
        then coalesce(
            try(decode(from_hex(array_to_string(
                list_transform(string_split({{ texte }}, ''), c -> lpad(hex(unicode(c)), 2, '0')), ''
            )))),
            {{ texte }}
        )
        else {{ texte }}
    end
{%- endmacro %}
