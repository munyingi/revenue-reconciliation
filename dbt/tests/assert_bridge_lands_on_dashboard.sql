-- Walking the waterfall from the CFO number must land exactly on the dashboard number.
with last_step as (
    select running_total_eur from {{ ref('recon_bridge') }} where step_order = 98
),
dashboard as (
    select amount_eur from {{ ref('recon_bridge') }} where step_type = 'end'
)
select l.running_total_eur, d.amount_eur
from last_step l cross join dashboard d
where l.running_total_eur <> d.amount_eur
