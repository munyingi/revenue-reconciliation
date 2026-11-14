-- Full outer join so that payments with no order (and orders with no payment yet) are kept.
select
    coalesce(o.order_id, p.order_id)                     as order_id,
    o.order_id is not null                               as has_order,
    p.payment_id,
    o.created_at_helsinki,
    o.currency,
    o.payment_method,
    o.order_status,
    o.order_total_eur,
    coalesce(p.payment_status, 'pending')                as payment_status,
    p.captured_at_utc,
    p.captured_at_helsinki,
    p.settled_amount_eur,
    p.failed_at_utc
from {{ ref('stg_shop__orders') }} o
full outer join {{ ref('int_payments') }} p
    on o.order_id = p.order_id
