select
    refund_id,
    payment_id,
    amount_eur                                            as refund_amount_eur,
    reason                                                as refund_reason,
    requested_at_utc,
    processed_at_utc,
    {{ utc_to_helsinki('processed_at_utc') }}             as processed_at_helsinki,
    status                                                as refund_status
from {{ source('raw', 'refunds') }}
