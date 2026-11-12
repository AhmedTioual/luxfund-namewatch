-- Headline figures for the dashboard (one row).
with d as (select * from {{ ref('dim_fund') }}),
r as (select * from {{ ref('fct_renames') }}),
since as (select * from r where change_date >= cast('{{ var("esma_publication_date") }}' as date))
select
    (select count(*) from d)                                               as funds,
    (select count(*) from d where entity_status = 'ACTIVE')                as active_funds,
    (select count(*) from d where has_esg_term)                            as esg_named_now,
    (select count(*) from d where has_esg_term and entity_status = 'ACTIVE') as esg_named_active,
    (select count(*) from d where history_checked)                         as history_checked,
    (select count(*) from r)                                               as real_renames,
    (select count(*) from since)                                           as renames_since_esma,
    (select count(distinct lei) from since where category in ('esg_removed', 'esg_to_vague')) as funds_dropped_esg,
    (select count(distinct lei) from since where category = 'esg_to_vague') as funds_esg_to_vague,
    (select count(distinct lei) from since where category = 'esg_added')   as funds_added_esg,
    (select count(*) from r where category_source = 'llm')                 as llm_classified,
    (select count(*) from d where manager_lei is not null or manager_name is not null) as funds_with_manager,
    (select count(*) from d where entity_status = 'ACTIVE' and (manager_lei is not null or manager_name is not null))
                                                                           as active_funds_with_manager,
    (select count(distinct coalesce(manager_lei, manager_name)) from d)     as managers,
    (select count(*) from d where umbrella_lei is not null)                as funds_with_umbrella,
    (select max(change_date) from r)                                       as latest_change_date,
    cast('{{ var("esma_publication_date") }}' as date)                     as esma_publication_date,
    cast('{{ var("esma_existing_funds_date") }}' as date)                  as esma_existing_funds_date
