-- Pipeline health shown on the "Data & method" page.
with ch as (select * from {{ ref('stg_name_changes') }}),
last_name as (
    select lei, arg_max(new_name, change_date) as last_new_name from ch group by lei
),
chain as (
    select count(*) filter (where {{ normalize_name('l.last_new_name') }} <> f.name_normalized) as mismatches,
           count(*) as funds_with_changes
    from last_name l join {{ ref('stg_funds') }} f using (lei)
)
select
    (select count(*) from {{ source('raw', 'funds') }})                 as raw_fund_rows,
    (select count(*) from {{ ref('stg_funds') }})                       as clean_funds,
    (select count(*) from {{ source('raw', 'name_changes') }})          as raw_change_rows,
    (select count(*) from ch)                                           as clean_changes,
    (select count(*) from {{ source('raw', 'name_changes') }}
     where lower(coalesce(field, '')) like '%lang%' or {{ is_language_tag('old_name') }} or {{ is_language_tag('new_name') }})
                                                                        as language_tag_changes_excluded,
    (select count(*) from ch where is_formatting_only)                  as formatting_only_changes,
    (select count(*) from ch where not is_formatting_only)              as real_changes,
    (select count(*) from {{ ref('stg_history_checked') }})             as funds_history_checked,
    (select mismatches from chain)                                      as name_chain_mismatches,
    (select funds_with_changes from chain)                              as funds_with_changes,
    (select max(loaded_at) from {{ ref('stg_load_log') }})              as last_loaded_at
