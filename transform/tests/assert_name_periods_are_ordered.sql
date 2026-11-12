-- A name period cannot end before it starts.
select * from {{ ref('int_name_history') }}
where valid_to is not null and valid_to < valid_from
