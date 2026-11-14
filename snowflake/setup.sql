-- One-time Snowflake setup. Run as ACCOUNTADMIN (or a role with CREATE ROLE / WAREHOUSE / DATABASE).
-- Replace <YOUR_USER> before running.

use role accountadmin;

create role if not exists RECON_ROLE;
grant role RECON_ROLE to user <YOUR_USER>;

create warehouse if not exists RECON_WH
  warehouse_size = 'XSMALL'
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true;
grant usage, operate on warehouse RECON_WH to role RECON_ROLE;

create database if not exists REVENUE_RECON;
grant ownership on database REVENUE_RECON to role RECON_ROLE copy current grants;

use role RECON_ROLE;
use database REVENUE_RECON;
create schema if not exists RAW;        -- source extracts (pipeline/load_raw.py)
-- dbt creates STAGING, INTERMEDIATE, REPORTS, RECONCILIATION and TEST_FIXTURES itself.
