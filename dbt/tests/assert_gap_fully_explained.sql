-- Fails if any part of the gap between the two reports is not covered by a labelled line item.
select *
from {{ ref('recon_summary') }}
where unexplained_eur <> 0
   or unexplained_eur is null
   or gap_eur is null
