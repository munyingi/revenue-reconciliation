select
    event_id,
    payment_id,
    merchant_reference,
    -- PSP reference 'ORD00100123' -> shop order_id 100123
    cast(substr(merchant_reference, 4) as integer)        as order_id,
    replace(event_type, 'payment.', '')                   as event_status,
    payment_method,
    currency,
    amount_local,
    settled_amount_eur,
    event_timestamp_utc                                   as event_at_utc,
    {{ utc_to_helsinki('event_timestamp_utc') }}          as event_at_helsinki,
    received_at_utc
from {{ source('raw', 'psp_payment_events') }}
