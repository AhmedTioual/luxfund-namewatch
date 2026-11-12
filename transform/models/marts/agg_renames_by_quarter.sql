-- Renames per quarter, split by category (for the timeline chart).
with q as (
    select range as quarter_start
    from range(cast('{{ var("history_start") }}' as date), current_date + interval 1 day, interval 3 month)
)
select
    q.quarter_start,
    year(q.quarter_start) || '-Q' || quarter(q.quarter_start)               as quarter,
    count(r.change_id)                                                    as renames,
    count(r.change_id) filter (where r.category = 'esg_removed')           as esg_removed,
    count(r.change_id) filter (where r.category = 'esg_to_vague')          as esg_to_vague,
    count(r.change_id) filter (where r.category = 'esg_reworded')          as esg_reworded,
    count(r.change_id) filter (where r.category = 'esg_added')             as esg_added,
    count(r.change_id) filter (where r.category = 'other_rename')          as other_rename
from q
left join {{ ref('fct_renames') }} r
    on r.change_date >= q.quarter_start and r.change_date < q.quarter_start + interval 3 month
group by 1, 2
order by 1
