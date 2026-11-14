-- Replica of the Sales dashboard logic, flaws included:
--   * months are Helsinki calendar months (order system clock)
--   * every order counts as revenue the moment it is placed, paid or not
--   * refunds are netted as soon as customer service approves them on the order
select
    date_trunc('month', created_at_helsinki)              as revenue_month,
    count(*)                                              as order_count,
    sum(order_total_eur)                                  as gross_sales_eur,
    sum(refunded_amount_eur)                              as approved_refunds_eur,
    sum(order_total_eur - refunded_amount_eur)            as net_sales_eur
from {{ ref('stg_shop__orders') }}
group by 1
