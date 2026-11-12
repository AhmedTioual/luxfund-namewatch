-- One row per real legal-name change, classified.
select
    r.change_id,
    r.lei,
    d.legal_name                                   as current_name,
    d.entity_status,
    d.name_prefix,
    d.manager_lei,
    d.manager_name,
    r.change_date,
    year(r.change_date)                            as change_year,
    year(r.change_date) || '-Q' || quarter(r.change_date) as change_quarter,
    case
        when r.change_date < cast('{{ var("esma_publication_date") }}' as date) then '1. Before ESMA guidelines'
        when r.change_date < cast('{{ var("esma_existing_funds_date") }}' as date) then '2. Transition period'
        else '3. After the deadline'
    end                                            as esma_phase,
    r.old_name,
    r.new_name,
    r.old_esg_terms,
    r.new_esg_terms,
    r.esg_terms_dropped,
    r.esg_terms_added,
    r.vague_terms_added,
    r.rule_category,
    r.ai_category,
    r.ai_confidence,
    r.ai_rationale,
    r.category,
    r.category_source,
    r.is_esg_candidate,
    r.category in ('esg_removed', 'esg_to_vague', 'esg_reworded', 'esg_added') as is_esg_rename
from {{ ref('int_renames_classified') }} r
left join {{ ref('dim_fund') }} d on d.lei = r.lei
