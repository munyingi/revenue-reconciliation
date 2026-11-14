{#
  Timezone and period helpers.
  Shop timestamps are naive Helsinki wall-clock time; PSP and refund timestamps are naive UTC.
  Snowflake is the production target; DuckDB is used for local runs and CI.
#}

{% macro utc_to_helsinki(column) -%}
    {{ return(adapter.dispatch('utc_to_helsinki')(column)) }}
{%- endmacro %}

{% macro default__utc_to_helsinki(column) -%}
    convert_timezone('UTC', 'Europe/Helsinki', {{ column }})
{%- endmacro %}

{% macro duckdb__utc_to_helsinki(column) -%}
    timezone('Europe/Helsinki', timezone('UTC', {{ column }}))
{%- endmacro %}


{% macro recon_period_start() -%}
    cast('{{ var("recon_month") }}' as timestamp)
{%- endmacro %}

{% macro recon_period_end() -%}
    {%- set d = modules.datetime.datetime.strptime(var("recon_month"), "%Y-%m-%d") -%}
    {%- set y = d.year + 1 if d.month == 12 else d.year -%}
    {%- set m = 1 if d.month == 12 else d.month + 1 -%}
    cast('{{ "%04d-%02d-01" % (y, m) }}' as timestamp)
{%- endmacro %}

{% macro in_recon_period(column) -%}
    ({{ column }} >= {{ recon_period_start() }} and {{ column }} < {{ recon_period_end() }})
{%- endmacro %}
