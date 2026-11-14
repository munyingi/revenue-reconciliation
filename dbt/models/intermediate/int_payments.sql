-- One row per PSP payment with its final outcome (first delivery of each event only).
with events as (
    select * from {{ ref('int_payment_events__deduplicated') }}
    where not is_duplicate_delivery
)

select
    payment_id,
    max(order_id)                                                          as order_id,
    case
        when max(case when event_status = 'captured' then 1 else 0 end) = 1 then 'captured'
        when max(case when event_status = 'failed'   then 1 else 0 end) = 1 then 'failed'
        when max(case when event_status = 'expired'  then 1 else 0 end) = 1 then 'expired'
    end                                                                    as payment_status,
    max(case when event_status = 'captured' then event_at_utc end)         as captured_at_utc,
    max(case when event_status = 'captured' then event_at_helsinki end)    as captured_at_helsinki,
    max(case when event_status = 'captured' then settled_amount_eur end)   as settled_amount_eur,
    max(case when event_status in ('failed', 'expired') then event_at_utc end) as failed_at_utc
from events
group by payment_id
