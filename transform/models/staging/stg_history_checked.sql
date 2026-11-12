select distinct upper(trim(lei)) as lei
from {{ source('raw', 'history_checked') }}
where lei is not null
