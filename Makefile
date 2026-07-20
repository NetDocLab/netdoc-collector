# Makefile
.PHONY: install uninstall check coverage doc fmt lint tests

install:
	poetry install --no-interaction --no-ansi
	poetry run pre-commit install
	poetry run pre-commit install --hook-type commit-msg

uninstall:
	poetry run pre-commit uninstall
	poetry run pre-commit uninstall --hook-type commit-msg

check: ## Run all pre-commit tests
	poetry run pre-commit run --all-files

coverage: ## Run tests and show coverage report (TODO: increase to 80)
	poetry run pytest tests --cov=netdoc_sdk --cov-report=term-missing --cov-fail-under=70

doc:  ## build the documentation into site/
	poetry run mkdocs build --strict

fmt: ## Code formatting
	poetry run ruff format .
	poetry run ruff check --fix

lint: ## Code linting (check only)
	poetry run ruff check . --output-format=full
	poetry run mypy src/

tests: ## Run tests (pytest only)
	poetry run pytest tests/unit -v --tb=short
	poetry run pytest tests/integration -v --tb=short

update: ## Update poetry, SBOM, SDK
	poetry add netdoc-sdk@latest
	poetry lock
	poetry run cyclonedx-py poetry --without dev -o sbom-cyclonedx.json
