# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] – 2026-10-20 – Milestone 1: foundations and bulk ingestion

### Added
- Project scaffold: uv, ruff, mypy (strict), pytest, pre-commit, Makefile, GitHub Actions CI.
- `finfacts` CLI: `check-env`, `universe`, `backfill`.
- SEC client with an 8 req/s token bucket, mandatory User-Agent, retries with backoff on 403/429/5xx and network errors, and atomic, cached streaming downloads.
- S&P 500 universe snapshot joined to SEC CIKs (`config/universe/`).
- Bulk backfill from `companyfacts.zip` and `submissions.zip` into immutable, gzipped, per-CIK bronze files partitioned by SEC snapshot date. Reruns are no-ops.
- `DATA_LICENSES.md`, MIT licence, `PLAN.md`.
