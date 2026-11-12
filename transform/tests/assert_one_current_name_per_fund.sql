-- Each fund has exactly one open-ended (current) name period.
select lei, count(*) as current_periods
from {{ ref('int_name_history') }}
where is_current
group by lei
having count(*) <> 1
