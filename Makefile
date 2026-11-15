# One command runs exactly what CI runs: `make check`.
# CI calls the same targets one per job, so a green `make check` means a green PR.

UV  ?= uv
RUN := $(UV) run --locked

.PHONY: check sync lint format types noai secrets test coverage fixtures mutation health

check: sync lint types noai secrets test coverage

sync:
	$(UV) sync --locked

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format:
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

types:
	$(RUN) mypy --strict src/equity/rules src/equity/matching src/equity/schema src/equity/quality

noai:
	$(RUN) python ci/check_no_ai.py

secrets:
	$(RUN) python ci/secrets_scan.py

test:
	$(RUN) pytest --cov=equity --cov-branch --cov-report=term-missing:skip-covered --cov-report=json:coverage.json

coverage:
	$(RUN) python ci/check_coverage.py coverage.json ci/coverage_floors.toml

fixtures:
	$(RUN) python tests/fixtures/build_synthetic.py

# Nightly only (not PR gates).
mutation:
	$(RUN) mutmut run

health:
	$(RUN) python -m equity.adapters.health
