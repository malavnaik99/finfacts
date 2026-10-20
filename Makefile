.DEFAULT_GOAL := help
.PHONY: help setup check-env lint fmt typecheck test ci universe backfill-local

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

ci: lint typecheck test  ## Everything CI runs

universe:  ## Refresh the S&P 500 -> CIK snapshot in config/universe/
	uv run finfacts universe

backfill-local:  ## Download SEC bulk zips and land in-scope CIKs in data/bronze (idempotent)
	uv run finfacts backfill
