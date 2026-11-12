-- Since the ESMA guidelines were published: which ESG term was dropped, and what replaced it.
with r as (
    select * from {{ ref('fct_renames') }}
    where category in ('esg_removed', 'esg_to_vague', 'esg_reworded')
      and change_date >= cast('{{ var("esma_publication_date") }}' as date)
),
src as (select change_id, unnest(esg_terms_dropped) as dropped_term, vague_terms_added, esg_terms_added from r),
tgt as (
    select change_id, dropped_term, unnest(vague_terms_added) as replacement, 'vague word' as replacement_kind
    from src where len(vague_terms_added) > 0
    union all
    select change_id, dropped_term, unnest(esg_terms_added), 'other ESG term'
    from src where len(vague_terms_added) = 0 and len(esg_terms_added) > 0
    union all
    select change_id, dropped_term, '(nothing)', 'no replacement'
    from src where len(vague_terms_added) = 0 and len(esg_terms_added) = 0
)
select dropped_term, replacement, replacement_kind, count(distinct change_id) as renames
from tgt
group by 1, 2, 3
order by renames desc
