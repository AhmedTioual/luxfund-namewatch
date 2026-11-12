-- One row per Luxembourg fund, with its naming story.
with funds as (select * from {{ ref('stg_funds') }}),
checked as (select lei from {{ ref('stg_history_checked') }}),
renames as (
    select
        lei,
        count(*)                                                  as real_renames,
        max(change_date)                                          as last_rename_date,
        bool_or(category in ('esg_removed', 'esg_to_vague')
                and change_date >= cast('{{ var("esma_publication_date") }}' as date)) as dropped_esg_since_esma,
        arg_min(old_name, change_date)                            as earliest_known_name
    from {{ ref('int_renames_classified') }}
    group by lei
),
terms as (select * from {{ ref('int_name_terms') }}),
prefix as (
    -- first meaningful word of the name: a rough proxy for the fund house (labelled as such in the app)
    select lei,
           upper(list_filter(string_split(name_normalized, ' '),
                 lambda x: x not in ('the', 'fund', 'funds', 'global', 'sicav', 'fcp', ''))[1]) as name_prefix
    from funds
)
select
    f.lei,
    f.legal_name,
    f.entity_status,
    f.registration_status,
    f.legal_form_code,
    f.initial_registration_date,
    f.last_update_date,
    coalesce(p.name_prefix, '?')                        as name_prefix,
    t.esg_terms                                         as current_esg_terms,
    t.esma_categories                                   as current_esma_categories,
    t.vague_terms                                       as current_vague_terms,
    len(t.esg_terms) > 0                                as has_esg_term,
    c.lei is not null                                   as history_checked,
    coalesce(r.real_renames, 0)                         as real_renames,
    r.last_rename_date,
    coalesce(r.dropped_esg_since_esma, false)           as dropped_esg_since_esma,
    coalesce(r.earliest_known_name, f.legal_name)       as earliest_known_name,
    l.manager_lei,
    l.manager_name,
    l.manager_country,
    l.manager_source,
    l.umbrella_lei,
    l.umbrella_name,
    l.master_lei,
    l.master_name
from funds f
left join terms t on t.name = f.legal_name
left join checked c on c.lei = f.lei
left join renames r on r.lei = f.lei
left join prefix p on p.lei = f.lei
left join {{ ref('int_fund_links') }} l on l.lei = f.lei
