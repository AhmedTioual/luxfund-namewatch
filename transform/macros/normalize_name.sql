{# Name used to compare two legal names: no case, accents, punctuation or legal-form spelling. #}
{% macro normalize_name(col) -%}
trim(regexp_replace(
    regexp_replace(
        regexp_replace(lower(strip_accents(coalesce({{ col }}, ''))), '[^a-z0-9]+', ' ', 'g'),
        '\b(s a r l|s a|sarl|sa|sicav|sicaf|scsp|scs|fcp|sca|raif|sif|lux|luxembourg)\b', ' ', 'g'),
    '\s+', ' ', 'g'))
{%- endmacro %}
