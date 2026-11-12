-- One clean row per Luxembourg fund LEI.
with src as (
    select *, row_number() over (partition by lei order by last_update desc nulls last) as rn
    from {{ source('raw', 'funds') }}
    where lei is not null and length(trim(lei)) = 20
)
select
    upper(trim(lei))                                  as lei,
    trim(legal_name)                                  as legal_name,
    {{ normalize_name('legal_name') }}                as name_normalized,
    nullif(trim(previous_names), '')                  as previous_names_recorded,
    nullif(trim(legal_form), '')                      as legal_form_code,
    coalesce(nullif(trim(entity_status), ''), 'UNKNOWN')       as entity_status,
    coalesce(nullif(trim(registration_status), ''), 'UNKNOWN') as registration_status,
    try_cast(left(initial_registration, 10) as date)  as initial_registration_date,
    try_cast(left(last_update, 10) as date)           as last_update_date
from src
where rn = 1
