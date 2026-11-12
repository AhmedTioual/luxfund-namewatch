-- Type-2 history of each fund's legal name: one row per period with valid_from / valid_to.
-- Built from the dated changes, so we can ask "what was this fund called on date X?".
with funds as (select * from {{ ref('stg_funds') }}),
ch as (
    select
        lei, change_id, change_date, old_name, new_name,
        row_number() over (partition by lei order by change_date, change_id) as rn,
        lead(change_date) over (partition by lei order by change_date, change_id) as next_date
    from {{ ref('stg_name_changes') }}
),
periods as (
    -- name before the first recorded change
    select ch.lei, ch.old_name as name,
           least(coalesce(f.initial_registration_date, date '1900-01-01'), ch.change_date) as valid_from,
           ch.change_date as valid_to
    from ch left join funds f using (lei)
    where ch.rn = 1
    union all
    -- name after each change, until the next one
    select lei, new_name, change_date, next_date from ch
    union all
    -- funds with no recorded change keep their current name
    select f.lei, f.legal_name, coalesce(f.initial_registration_date, date '1900-01-01'), null
    from funds f
    where not exists (select 1 from ch where ch.lei = f.lei)
)
select
    md5(p.lei || '|' || cast(p.valid_from as varchar) || '|' || p.name) as name_period_id,
    p.lei,
    p.name,
    p.valid_from,
    p.valid_to,
    p.valid_to is null as is_current,
    len(t.esg_terms) > 0   as has_esg_term,
    len(t.vague_terms) > 0 as has_vague_term,
    t.esg_terms,
    t.vague_terms
from periods p
left join {{ ref('int_name_terms') }} t on t.name = p.name
