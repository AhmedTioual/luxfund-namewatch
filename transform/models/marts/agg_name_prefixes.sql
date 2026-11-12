-- Fund houses, approximated by the first word of the fund name.
with repl as (
    select name_prefix, unnest(vague_terms_added) as word
    from {{ ref('fct_renames') }}
    where category = 'esg_to_vague'
),
fav as (
    select name_prefix, arg_max(word, n) as favourite_replacement
    from (select name_prefix, word, count(*) as n from repl group by 1, 2)
    group by 1
)
select
    d.name_prefix,
    count(*)                                                       as funds,
    count(*) filter (where d.entity_status = 'ACTIVE')             as active_funds,
    count(*) filter (where d.has_esg_term)                         as esg_named_now,
    count(*) filter (where d.dropped_esg_since_esma)               as dropped_esg_since_esma,
    any_value(fav.favourite_replacement)                           as favourite_replacement
from {{ ref('dim_fund') }} d
left join fav on fav.name_prefix = d.name_prefix
group by d.name_prefix
having count(*) >= 5
order by dropped_esg_since_esma desc, esg_named_now desc
