select
    order_id,
    order_number,
    created_at                as created_at_helsinki,
    customer_country,
    currency,
    order_total_local,
    order_total_eur,
    payment_method,
    status                    as order_status,
    refunded_amount_eur
from {{ source('raw', 'shop_orders') }}
