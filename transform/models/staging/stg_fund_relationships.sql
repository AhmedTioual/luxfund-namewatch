-- Fund links from GLEIF: manager (IS_FUND-MANAGED_BY), umbrella (IS_SUBFUND_OF), master fund (IS_FEEDER_TO),
-- plus the manager some funds declare as "associated entity" in their own LEI record.
select distinct
    upper(trim(fund_lei))                                     as fund_lei,
    nullif(upper(trim(related_lei)), '')                      as related_lei,
    nullif(trim(related_name), '')                            as related_name,
    case
        when relationship_type in ('IS_FUND-MANAGED_BY', 'ASSOCIATED_FUND_FAMILY') then 'manager'
        when relationship_type = 'IS_SUBFUND_OF' then 'umbrella'
        when relationship_type = 'IS_FEEDER_TO' then 'master'
    end                                                       as link,
    relationship_type,
    coalesce(nullif(upper(trim(relationship_status)), ''), 'ACTIVE') as relationship_status,
    try_cast(left(start_date, 10) as date)                    as start_date,
    source
from {{ source('raw', 'fund_relationships') }}
where fund_lei is not null
  and relationship_type in ('IS_FUND-MANAGED_BY', 'ASSOCIATED_FUND_FAMILY', 'IS_SUBFUND_OF', 'IS_FEEDER_TO')
  and (nullif(trim(related_lei), '') is not null or nullif(trim(related_name), '') is not null)
