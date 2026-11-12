-- Dated legal-name changes, de-duplicated, with a flag for formatting-only changes
-- (case, accents, punctuation or legal-form spelling).
-- Changes to the name's language tag (xml:lang, e.g. "lb" -> "de") are not renames and are removed:
-- GLEIF records them on the same LegalName field.
with src as (
    select distinct
        upper(trim(lei))                      as lei,
        try_cast(left("date", 10) as date)    as change_date,
        trim(old_name)                        as old_name,
        trim(new_name)                        as new_name
    from {{ source('raw', 'name_changes') }}
    where old_name is not null and new_name is not null and trim(old_name) <> trim(new_name)
      and lower(coalesce(field, '')) not like '%lang%'
      and not {{ is_language_tag('old_name') }}
      and not {{ is_language_tag('new_name') }}
)
select
    md5(lei || '|' || coalesce(cast(change_date as varchar), '') || '|' || old_name || '|' || new_name) as change_id,
    lei,
    change_date,
    old_name,
    new_name,
    {{ normalize_name('old_name') }} as old_normalized,
    {{ normalize_name('new_name') }} as new_normalized,
    {{ normalize_name('old_name') }} = {{ normalize_name('new_name') }} as is_formatting_only
from src
where change_date is not null
