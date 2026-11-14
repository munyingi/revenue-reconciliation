{#
  Every individual difference between the Sales dashboard and the CFO report for var('recon_month'),
  one row per order / payment event / refund, each with a label explaining why.

  difference_eur = dashboard_amount_eur - cfo_amount_eur
  Sum of difference_eur over all rows = dashboard total - CFO total (checked in recon_summary).
#}

with orders as (
    select
        *,
        {{ in_recon_period('created_at_helsinki') }}                         as in_dashboard,
        payment_status = 'captured' and {{ in_recon_period('captured_at_utc') }} as in_cfo
    from {{ ref('int_orders__matched_to_payments') }}
),

order_lines as (
    select
        'order'                                                              as line_source,
        cast(order_id as varchar)                                            as source_id,
        order_id,
        payment_id,
        cast(null as varchar)                                                as refund_id,
        cast(null as varchar)                                                as event_id,
        payment_method,
        created_at_helsinki                                                  as order_created_at_helsinki,
        captured_at_utc                                                      as money_moved_at_utc,
        captured_at_helsinki                                                 as money_moved_at_helsinki,
        case when in_dashboard then order_total_eur else 0 end               as dashboard_amount_eur,
        case when in_cfo then settled_amount_eur else 0 end                  as cfo_amount_eur,
        case
            when not has_order                                   then 'unmatched_payment'
            when in_dashboard and payment_status in ('failed', 'expired') then 'failed_payment'
            when in_dashboard and payment_status = 'pending'     then 'payment_timing_lag'
            when in_dashboard and in_cfo                         then 'fx_difference'
            -- in one report but not the other: same Helsinki month means only the clock differs
            when date_trunc('month', captured_at_helsinki)
               = date_trunc('month', created_at_helsinki)        then 'timezone_shift'
            else 'payment_timing_lag'
        end                                                                  as difference_type
    from orders
),

duplicate_lines as (
    select
        'payment_event'                                                      as line_source,
        event_id                                                             as source_id,
        order_id,
        payment_id,
        cast(null as varchar)                                                as refund_id,
        event_id,
        payment_method,
        cast(null as timestamp)                                              as order_created_at_helsinki,
        event_at_utc                                                         as money_moved_at_utc,
        event_at_helsinki                                                    as money_moved_at_helsinki,
        0                                                                    as dashboard_amount_eur,
        settled_amount_eur                                                   as cfo_amount_eur,
        'duplicate_payment'                                                  as difference_type
    from {{ ref('int_payment_events__deduplicated') }}
    where is_duplicate_delivery
      and event_status = 'captured'
      and {{ in_recon_period('event_at_utc') }}
),

refunds as (
    select
        *,
        {{ in_recon_period('order_created_at_helsinki') }}                   as netted_by_dashboard,
        refund_status = 'processed' and {{ in_recon_period('processed_at_utc') }} as netted_by_cfo
    from {{ ref('int_refunds__matched_to_orders') }}
),

refund_lines as (
    select
        'refund'                                                             as line_source,
        refund_id                                                            as source_id,
        order_id,
        payment_id,
        refund_id,
        cast(null as varchar)                                                as event_id,
        cast(null as varchar)                                                as payment_method,
        order_created_at_helsinki,
        processed_at_utc                                                     as money_moved_at_utc,
        processed_at_helsinki                                                as money_moved_at_helsinki,
        case when netted_by_dashboard then -refund_amount_eur else 0 end     as dashboard_amount_eur,
        case when netted_by_cfo then -refund_amount_eur else 0 end           as cfo_amount_eur,
        case
            when order_id is null                                then 'unmatched_refund'
            when netted_by_dashboard and not netted_by_cfo       then 'refund_not_yet_processed'
            else 'refund_prior_period_order'
        end                                                                  as difference_type
    from refunds
),

all_lines as (
    select * from order_lines
    union all
    select * from duplicate_lines
    union all
    select * from refund_lines
)

select
    line_source || '-' || source_id                                          as line_id,
    difference_type,
    line_source,
    order_id,
    payment_id,
    refund_id,
    event_id,
    payment_method,
    order_created_at_helsinki,
    money_moved_at_utc,
    money_moved_at_helsinki,
    cast(dashboard_amount_eur as decimal(12,2))                              as dashboard_amount_eur,
    cast(cfo_amount_eur as decimal(12,2))                                    as cfo_amount_eur,
    cast(dashboard_amount_eur - cfo_amount_eur as decimal(12,2))             as difference_eur
from all_lines
where dashboard_amount_eur - cfo_amount_eur <> 0
