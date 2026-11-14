-- Waterfall from the CFO number to the Sales dashboard number, one step per difference type.
with summary as (
    select * from {{ ref('recon_summary') }}
),

steps as (
    select
        difference_type,
        sum(difference_eur)                                as amount_eur,
        count(*)                                           as line_count
    from {{ ref('recon_line_items') }}
    group by difference_type
),

labels as (
    select * from (values
        ('failed_payment',            1, 'Failed payment',               'Order counted by the dashboard, but the card was declined or the bank transfer was never paid.'),
        ('payment_timing_lag',        2, 'Payment timing lag',           'Klarna / bank transfer money arrived in a different month than the order was placed.'),
        ('timezone_shift',            3, 'Timezone shift',               'Order near midnight: October in Helsinki time, September or November in UTC.'),
        ('refund_prior_period_order', 4, 'Refund on prior-period order', 'Refund paid out this month for an order from an earlier month. Finance deducts it, the dashboard does not.'),
        ('fx_difference',             5, 'FX difference',                'SEK / NOK order: the shop used its catalogue rate, the payment provider settled at its own rate.'),
        ('duplicate_payment',         6, 'Duplicate payment event',      'The payment provider sent the same capture twice. Finance counted it twice.'),
        ('refund_not_yet_processed',  7, 'Refund not yet processed',     'Refund approved in the shop (dashboard nets it) but money not yet returned (finance does not).'),
        ('unmatched_payment',         8, 'Unmatched payment',            'Payment with no matching order. Needs investigation.'),
        ('unmatched_refund',          9, 'Unmatched refund',             'Refund with no matching payment. Needs investigation.')
    ) as t(difference_type, sort_order, label, explanation)
),

bridge as (
    select
        0                                   as step_order,
        'start'                             as step_type,
        'cfo_report'                        as difference_type,
        'CFO report'                        as label,
        'Captured payments (UTC month) minus refunds processed (UTC month).' as explanation,
        s.cfo_total_eur                     as amount_eur,
        cast(null as integer)               as line_count
    from summary s

    union all

    select
        l.sort_order,
        'difference',
        st.difference_type,
        coalesce(l.label, st.difference_type),
        l.explanation,
        st.amount_eur,
        st.line_count
    from steps st
    left join labels l on st.difference_type = l.difference_type

    union all

    select 98, 'difference', 'unexplained', 'Unexplained',
           'Gap not covered by any labelled line. Must be exactly 0.', s.unexplained_eur, cast(null as integer)
    from summary s

    union all

    select 99, 'end', 'sales_dashboard', 'Sales dashboard',
           'Orders placed (Helsinki month) minus refunds approved on those orders.', s.dashboard_total_eur, cast(null as integer)
    from summary s
)

select
    *,
    sum(case when step_type <> 'end' then amount_eur else 0 end)
        over (order by step_order rows between unbounded preceding and current row) as running_total_eur
from bridge
