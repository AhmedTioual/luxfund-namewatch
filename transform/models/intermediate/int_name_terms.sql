-- Every distinct fund name (current or historical) with the ESG and "vague" terms it contains.
-- The vocabulary is a seed (seeds/esg_vocabulary.csv), so the rules are versioned and reviewable.
with names as (
    select legal_name as name from {{ ref('stg_funds') }}
    union
    select old_name from {{ ref('stg_name_changes') }}
    union
    select new_name from {{ ref('stg_name_changes') }}
),
norm as (
    select name, {{ normalize_name('name') }} as normalized from names where name is not null
),
hits as (
    select n.name, v.term, v.kind, v.esma_category
    from norm n
    join {{ ref('esg_vocabulary') }} v on regexp_matches(n.normalized, v.pattern)
)
select
    n.name,
    n.normalized,
    coalesce(list_sort(list(distinct h.term) filter (where h.kind = 'esg')), []::varchar[])          as esg_terms,
    coalesce(list_sort(list(distinct h.esma_category) filter (where h.kind = 'esg')), []::varchar[]) as esma_categories,
    coalesce(list_sort(list(distinct h.term) filter (where h.kind = 'vague')), []::varchar[])        as vague_terms
from norm n
left join hits h on h.name = n.name
group by n.name, n.normalized
