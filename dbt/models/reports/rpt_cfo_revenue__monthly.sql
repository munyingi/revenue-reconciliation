-- Replica of the CFO report logic, flaws included:
--   * months are UTC calendar months (payment provider and refund tool clocks)
--   * revenue = settled EUR from every capture event the PSP sent (duplicates included)
--   * refunds are deducted only when the money actually leaves (processed_at)
with captures as (
    select
        date_trunc('month', event_at_utc)                 as revenue_month,
        sum(settled_amount_eur)                           as captured_eur,
        count(*)                                          as capture_events
    from {{ ref('stg_psp__payment_events') }}
    where event_status = 'captured'
    group by 1
),

refunds as (
    select
        date_trunc('month', processed_at_utc)             as revenue_month,
        sum(refund_amount_eur)                            as refunds_paid_eur
    from {{ ref('stg_refunds__refunds') }}
    where refund_status = 'processed'
    group by 1
)

select
    coalesce(c.revenue_month, r.revenue_month)            as revenue_month,
    coalesce(c.capture_events, 0)                         as capture_events,
    coalesce(c.captured_eur, 0)                           as captured_eur,
    coalesce(r.refunds_paid_eur, 0)                       as refunds_paid_eur,
    coalesce(c.captured_eur, 0) - coalesce(r.refunds_paid_eur, 0) as net_revenue_eur
from captures c
full outer join refunds r on c.revenue_month = r.revenue_month
