-- Share of funds whose name contained an ESG term at each quarter end, using the name history.
-- Population: funds whose change history was checked and registered by that date.
with q as (
    select least((range + interval 3 month - interval 1 day)::date, current_date) as quarter_end
    from range(cast('{{ var("history_start") }}' as date), current_date, interval 3 month)
),
pop as (
    select h.*
    from {{ ref('int_name_history') }} h
    join {{ ref('dim_fund') }} d on d.lei = h.lei and d.history_checked
)
select
    q.quarter_end,
    year(q.quarter_end) || '-Q' || quarter(q.quarter_end)          as quarter,
    count(distinct p.lei)                                        as funds,
    count(distinct p.lei) filter (where p.has_esg_term)          as funds_with_esg_name,
    count(distinct p.lei) filter (where p.has_vague_term)        as funds_with_vague_name,
    round(100.0 * count(distinct p.lei) filter (where p.has_esg_term) / nullif(count(distinct p.lei), 0), 2) as esg_name_share
from q
join pop p on p.valid_from <= q.quarter_end and (p.valid_to is null or p.valid_to > q.quarter_end)
group by 1, 2
order by 1
