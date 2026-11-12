-- LLM decisions on ESG-related renames (empty when the AI step has not run).
select
    upper(trim(lei))                            as lei,
    try_cast(left(change_date, 10) as date)     as change_date,
    trim(old_name)                              as old_name,
    trim(new_name)                              as new_name,
    lower(trim(category))                       as ai_category,
    try_cast(old_is_esg as boolean)             as ai_old_is_esg,
    try_cast(new_is_esg as boolean)             as ai_new_is_esg,
    try_cast(confidence as double)              as ai_confidence,
    rationale                                   as ai_rationale,
    model                                       as ai_model
from {{ source('raw', 'name_classifications') }}
