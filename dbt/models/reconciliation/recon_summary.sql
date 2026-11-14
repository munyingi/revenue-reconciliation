-- Headline check: the gap between the two reports, how much of it is explained, and what is left.
with dashboard as (
    select net_sales_eur as dashboard_total_eur
    from {{ ref('rpt_sales_dashboard__monthly') }}
    where revenue_month = {{ recon_period_start() }}
),

cfo as (
    select net_revenue_eur as cfo_total_eur
    from {{ ref('rpt_cfo_revenue__monthly') }}
    where revenue_month = {{ recon_period_start() }}
),

explained as (
    select
        sum(difference_eur)                                as explained_eur,
        count(*)                                           as line_count
    from {{ ref('recon_line_items') }}
)

select
    {{ recon_period_start() }}                             as recon_month,
    d.dashboard_total_eur,
    c.cfo_total_eur,
    d.dashboard_total_eur - c.cfo_total_eur                as gap_eur,
    e.explained_eur,
    e.line_count                                           as explained_line_count,
    d.dashboard_total_eur - c.cfo_total_eur - e.explained_eur as unexplained_eur
from dashboard d
cross join cfo c
cross join explained e
