select * from {{ source('raw', 'load_log') }}
