-- The PSP sometimes delivers the same capture twice with a new event_id.
-- A payment can only be captured once, so the business key is (payment_id, event_status).
select
    *,
    row_number() over (
        partition by payment_id, event_status
        order by received_at_utc, event_id
    )                                                    as delivery_number,
    row_number() over (
        partition by payment_id, event_status
        order by received_at_utc, event_id
    ) > 1                                                as is_duplicate_delivery
from {{ ref('stg_psp__payment_events') }}
