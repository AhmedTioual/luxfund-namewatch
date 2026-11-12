{% test dbt_utils_free_single_row(model) %}
select count(*) as n from {{ model }} having count(*) <> 1
{% endtest %}
