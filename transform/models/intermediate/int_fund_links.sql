-- One row per fund with its manager, umbrella and master fund (current links only).
-- Manager priority: GLEIF relationship record first, then the fund's own LEI record.
with links as (
    select
        r.*,
        coalesce(e.legal_name, r.related_name)  as related_legal_name,
        e.country                               as related_country,
        row_number() over (
            partition by r.fund_lei, r.link
            order by case r.source when 'relationship_record' then 0 else 1 end,
                     r.start_date desc nulls last, r.related_lei
        ) as rn
    from {{ ref('stg_fund_relationships') }} r
    left join {{ ref('stg_related_entities') }} e on e.lei = r.related_lei
    where r.relationship_status <> 'INACTIVE'
)
select
    fund_lei as lei,
    max(related_lei)        filter (where link = 'manager')  as manager_lei,
    max(related_legal_name) filter (where link = 'manager')  as manager_name,
    max(related_country)    filter (where link = 'manager')  as manager_country,
    max(case source when 'relationship_record' then 'GLEIF relationship record' else 'Fund LEI record (associated entity)' end)
        filter (where link = 'manager')                      as manager_source,
    max(related_lei)        filter (where link = 'umbrella') as umbrella_lei,
    max(related_legal_name) filter (where link = 'umbrella') as umbrella_name,
    max(related_lei)        filter (where link = 'master')   as master_lei,
    max(related_legal_name) filter (where link = 'master')   as master_name
from links
where rn = 1
group by fund_lei
