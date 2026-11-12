with src as (
    select *, row_number() over (partition by upper(trim(lei)) order by legal_name) as rn
    from {{ source('raw', 'related_entities') }}
    where lei is not null
)
select
    upper(trim(lei))      as lei,
    trim(legal_name)      as legal_name,
    nullif(trim(country), '') as country,
    nullif(trim(category), '') as category,
    nullif(trim(entity_status), '') as entity_status
from src
where rn = 1
