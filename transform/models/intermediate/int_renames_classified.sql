-- Real renames (formatting-only changes removed) with the ESG terms dropped or added,
-- a rule-based category, and the LLM category when the AI step has run.
with ch as (
    select * from {{ ref('stg_name_changes') }} where not is_formatting_only
),
terms as (select * from {{ ref('int_name_terms') }}),
joined as (
    select
        ch.*,
        o.esg_terms   as old_esg_terms,
        n.esg_terms   as new_esg_terms,
        o.vague_terms as old_vague_terms,
        n.vague_terms as new_vague_terms
    from ch
    left join terms o on o.name = ch.old_name
    left join terms n on n.name = ch.new_name
),
diffs as (
    select
        *,
        list_filter(old_esg_terms, lambda x: not list_contains(new_esg_terms, x))     as esg_terms_dropped,
        list_filter(new_esg_terms, lambda x: not list_contains(old_esg_terms, x))     as esg_terms_added,
        list_filter(new_vague_terms, lambda x: not list_contains(old_vague_terms, x)) as vague_terms_added
    from joined
),
rules as (
    select
        *,
        case
            when len(old_esg_terms) > 0 and len(new_esg_terms) = 0 and len(vague_terms_added) > 0 then 'esg_to_vague'
            when len(old_esg_terms) > 0 and len(new_esg_terms) = 0 then 'esg_removed'
            when len(old_esg_terms) > 0 and len(new_esg_terms) > 0 and old_esg_terms <> new_esg_terms then 'esg_reworded'
            when len(old_esg_terms) = 0 and len(new_esg_terms) > 0 then 'esg_added'
            else 'other_rename'
        end as rule_category
    from diffs
)
select
    r.*,
    ai.ai_category,
    ai.ai_confidence,
    ai.ai_rationale,
    ai.ai_model,
    coalesce(ai.ai_category, r.rule_category)              as category,
    case when ai.ai_category is not null then 'llm' else 'rules' end as category_source,
    r.rule_category <> 'other_rename' or len(r.vague_terms_added) > 0 as is_esg_candidate
from rules r
left join {{ ref('stg_ai_classifications') }} ai
    on ai.lei = r.lei and ai.change_date = r.change_date and ai.old_name = r.old_name and ai.new_name = r.new_name
