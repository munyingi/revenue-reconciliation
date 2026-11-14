-- The dashboard nets refunds using the amount written on the order; the line items use the
-- refund system. If the two systems disagree on an amount, the reconciliation would be wrong.
with per_order as (
    select order_id, sum(refund_amount_eur) as refund_system_eur
    from {{ ref('int_refunds__matched_to_orders') }}
    group by order_id
)
select o.order_id, o.refunded_amount_eur, coalesce(p.refund_system_eur, 0) as refund_system_eur
from {{ ref('stg_shop__orders') }} o
left join per_order p on o.order_id = p.order_id
where o.refunded_amount_eur <> coalesce(p.refund_system_eur, 0)
