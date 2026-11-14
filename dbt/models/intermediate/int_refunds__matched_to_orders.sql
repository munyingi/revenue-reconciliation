-- Refunds only know the PSP payment_id. Walk refund -> payment -> order.
select
    r.refund_id,
    r.payment_id,
    p.order_id,
    o.created_at_helsinki                                as order_created_at_helsinki,
    r.refund_amount_eur,
    r.refund_status,
    r.requested_at_utc,
    r.processed_at_utc,
    r.processed_at_helsinki
from {{ ref('stg_refunds__refunds') }} r
left join {{ ref('int_payments') }} p on r.payment_id = p.payment_id
left join {{ ref('stg_shop__orders') }} o on p.order_id = o.order_id
