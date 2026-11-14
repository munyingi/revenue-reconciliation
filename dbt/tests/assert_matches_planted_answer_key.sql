-- The generator recorded the impact of every flaw it planted (seeds/answer_key.csv),
-- derived from the cause rather than from these SQL rules. The pipeline must find
-- exactly the same amount and number of lines for each difference type.
with found as (
    select difference_type, sum(difference_eur) as found_eur, count(*) as found_lines
    from {{ ref('recon_line_items') }}
    group by difference_type
)

select
    coalesce(f.difference_type, k.difference_type)   as difference_type,
    k.expected_amount_eur,
    f.found_eur,
    k.expected_line_count,
    f.found_lines
from found f
full outer join {{ ref('answer_key') }} k on f.difference_type = k.difference_type
where coalesce(f.found_eur, 0) <> coalesce(k.expected_amount_eur, 0)
   or coalesce(f.found_lines, 0) <> coalesce(k.expected_line_count, 0)
