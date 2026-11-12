-- Fund houses from GLEIF's fund-manager links: one row per management company.
with d as (
    select *, coalesce(manager_lei, 'name:' || manager_name) as manager_key
    from {{ ref('dim_fund') }}
    where manager_lei is not null or manager_name is not null
),
repl as (
    select d.manager_key, unnest(r.vague_terms_added) as word
    from {{ ref('fct_renames') }} r join d on d.lei = r.lei
    where r.category = 'esg_to_vague'
),
fav as (
    select manager_key, arg_max(word, n) as favourite_replacement
    from (select manager_key, word, count(*) as n from repl group by 1, 2)
    group by 1
)
select
    d.manager_key,
    any_value(d.manager_lei)                                     as manager_lei,
    any_value(d.manager_name)                                    as manager_name,
    any_value(d.manager_country)                                 as manager_country,
    count(*)                                                     as funds,
    count(*) filter (where d.entity_status = 'ACTIVE')           as active_funds,
    count(*) filter (where d.has_esg_term)                       as esg_named_now,
    count(*) filter (where d.dropped_esg_since_esma)             as dropped_esg_since_esma,
    count(distinct d.name_prefix)                                as name_prefixes,
    count(distinct d.umbrella_lei)                               as umbrellas,
    any_value(fav.favourite_replacement)                         as favourite_replacement
from d
left join fav on fav.manager_key = d.manager_key
group by d.manager_key
order by dropped_esg_since_esma desc, funds desc
