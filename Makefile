# Usage:  make all                 (local DuckDB, no account needed)
#         make all TARGET=snowflake (needs .env loaded, see README)
TARGET ?= duckdb
export DBT_TARGET := $(TARGET)

.PHONY: all data load dbt export report app clean

all: data load dbt export report

data:
	python generator/generate_data.py

load:
	python pipeline/load_raw.py --target $(TARGET)

dbt:
	cd dbt && dbt build --profiles-dir . --target $(TARGET)

export:
	python pipeline/export_marts.py --target $(TARGET)

report:
	python reports/build_report.py

app:
	streamlit run app/streamlit_app.py

clean:
	rm -rf data/warehouse.duckdb dbt/target dbt/logs
