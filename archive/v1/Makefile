# PolyCrawler development convenience targets.
# Requires `make` (GNU Make). On Windows use PowerShell: .\scripts\dev.ps1

.PHONY: install lint typecheck test test-cov migrate db-up db-down run dev

SHELL := /bin/bash
PYTHON := python
ALEMBIC := alembic

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

test:
	pytest -v

test-cov:
	pytest --cov=src/poly_crawler --cov-report=term-missing

migrate:
	$(ALEMBIC) upgrade head

db-up:
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

db-down:
	$(ALEMBIC) downgrade -1

run:
	uvicorn poly_crawler.main:app --reload

dev: install lint typecheck test
