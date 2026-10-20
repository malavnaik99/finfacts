.DEFAULT_GOAL := help
.PHONY: help setup check-env lint fmt typecheck test ci universe backfill-local incremental \
        flatten build dbt-ci fixtures

DBT := uv run dbt --no-use-colors
DBT_ARGS := --project-dir dbt --profiles-dir dbt

help:  ## List targets
	@uv run python -c "import re;[print(f'{m[0]:<16} {m[1]}') for m in re.findall(r'^([a-z-]+):.*?## (.*)$$', open('Makefile').read(), re.M)]"

setup:  ## Install the locked environment and git hooks
	uv sync --locked
	uv run pre-commit install

check-env:  ## Validate .env / environment (no secrets printed)
	uv run finfacts check-env

lint:  ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Auto-format
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## mypy --strict
	uv run mypy

test:  ## Unit tests (no network)
	uv run pytest

ci: lint typecheck test dbt-ci  ## Everything CI runs

universe:  ## Refresh the S&P 500 -> CIK snapshot in config/universe/
	uv run finfacts universe

backfill-local:  ## Download SEC bulk zips and land in-scope CIKs in data/bronze (idempotent)
	uv run finfacts backfill

incremental:  ## Daily load: pull companyfacts only for CIKs with new 10-K/10-Q (idempotent)
	uv run finfacts incremental

flatten:  ## Convert new bronze JSON to parquet (idempotent)
	uv run finfacts flatten

build: flatten  ## Flatten + dbt build (models and tests) on local DuckDB
	$(DBT) build $(DBT_ARGS)

# CI: same pipeline on committed fixtures (5 real CIKs, trimmed), isolated in build/ci.
dbt-ci: export DATA_DIR := build/ci
dbt-ci: export FINFACTS_DUCKDB_PATH := build/ci/finfacts.duckdb
dbt-ci: export SEC_USER_AGENT := FinFacts-ci/0.1 ci@example.com
dbt-ci:  ## dbt build on committed fixtures (offline)
	uv run python -c "import shutil; shutil.rmtree('build/ci', ignore_errors=True); shutil.copytree('tests/fixtures/bronze', 'build/ci/bronze')"
	uv run finfacts flatten
	$(DBT) build $(DBT_ARGS)

fixtures:  ## Regenerate tests/fixtures from the local backfill
	uv run python scripts/make_fixtures.py
