{# True when a value is a language code such as "en", "de", "lb" or "fr-LU" rather than a fund name. #}
{% macro is_language_tag(col) -%}
regexp_full_match(trim(coalesce({{ col }}, '')), '[a-z]{2,3}(-[A-Za-z0-9]{2,8})*')
{%- endmacro %}
