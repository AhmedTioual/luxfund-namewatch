-- A language code ("en", "de", "lb") must never appear as a fund name in the name history.
select * from {{ ref('int_name_history') }}
where {{ is_language_tag('name') }}
