# Contributing to netdoc-collector

Thank you for your interest in contributing. This document covers the development
workflow, tooling, and conventions used in this project.

---

## Table of Contents

- [Requirements](#requirements)
- [Local Setup](#local-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Commit Convention](#commit-convention)
- [Running Unit Tests](#running-unit-tests)
- [Running Integration Tests](#running-integration-tests)
- [Code Quality](#code-quality)
- [Releasing](#releasing)

---

## Requirements

- Python `>=3.12, <3.14`
- [Poetry](https://python-poetry.org/) for dependency management
- [pre-commit](https://pre-commit.com/) for local code quality hooks

---

## Local Setup

```bash
# Clone the repository
git clone https://github.com/netdoclab/netdoc-collector.git
cd netdoc-collector

# Install dependencies (including dev extras)
poetry install

# Install pre-commit hooks
pre-commit install
pre-commit install --hook-type commit-msg

# Verify the setup
make check
```

---

## Project Structure

```text
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── README.md
├── config-example.yaml
├── inventory-example.json
├── mkdocs.yml
├── nornir.log
├── poetry.lock
├── pyproject.toml
├── release-please-config.json
├── secrets-example.yaml
├── src
│   └── netdoc_collector
│       ├── __init__.py
│       ├── __main__.py
│       ├── core
│       │   ├── __init__.py
│       │   ├── ansible_inventory.py
│       │   ├── scanner.py
│       │   ├── tasks.py
│       │   └── utils.py
│       ├── main.py
│       └── plugins
│           ├── __init__.py
│           ├── base.py
│           ├── dispatcher.py
│           ├── netmiko_allied_telesis_awplus.py
│           ├── netmiko_aruba_oscx.py
│           ├── netmiko_cisco_ios.py
│           ├── netmiko_cisco_nxos.py
│           ├── netmiko_cisco_xr.py
│           ├── netmiko_hp_comware.py
│           ├── netmiko_hp_procurve.py
│           ├── netmiko_huawei_vrp.py
│           └── netmiko_linux.py
└── tests
```

---

## Development Workflow

Every change — no matter how small — follows this flow:

### 1. Create a branch

Branch names should reflect the type and scope of the change:

```bash
git checkout -b fix/null-value-credential-serializer
git checkout -b feat/retry-logic-5xx
git checkout -b chore/bump-httpx-0-27
```

### 2. Make your change

Keep changes small and focused. One logical change per commit.
Add or update tests in `tests/` to cover your change.

### 3. Check locally

Run all pre-commit hooks before pushing:

```bash
make check       # pre-commit run --all-files
make test        # pytest with coverage
```

Both commands must pass cleanly before opening a pull request.

### 4. Commit

Follow the [Conventional Commits](#commit-convention) format.
The `conventional-pre-commit` hook will reject commits that do not comply.

### 5. Open a pull request

- Target branch: `main`
- The CI pipeline runs automatically on every push
- The pull request cannot be merged until CI is green and at least one review is approved

### 6. Merge

Merges use **squash merge** to keep `main` linear.
The branch is deleted after merge.

### 7. Release

`release-please` analyses commits on `main` after each merge and either:

- Updates the pending release pull request, or
- Creates a new one if none exists.

Merging the release pull request triggers the CD pipeline:
creates the git tag, publishes the GitHub Release, and uploads to PyPI.

---

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/).
The format is:

```text
<type>[optional scope]: <short description>

[optional body]

[optional footer]
```

### Types

| Type | When to use | Version bump |
|---|---|---|
| `feat` | New feature | `minor` |
| `fix` | Bug fix | `patch` |
| `chore` | Maintenance, dependencies, config | none |
| `docs` | Documentation only | none |
| `refactor` | Code change with no behaviour change | none |
| `test` | Add or update tests | none |
| `ci` | CI/CD pipeline changes | none |
| `build` | Build system or packaging | none |
| `perf` | Performance improvement | none |

### Scope

Use the module name as scope:

```text
feat(client):     src/netdoc_sdk/client.py
fix(models):      src/netdoc_sdk/models.py
fix(exceptions):  src/netdoc_sdk/exceptions.py
chore(builders):  src/netdoc_sdk/builders.py
```

### Examples

```bash
# New feature → 0.1.9 → 0.2.0
git commit -m "feat(client): add retry logic on 5xx responses"

# Bug fix → 0.1.9 → 0.1.10
git commit -m "fix(models): handle null value in credential serializer"

# Dependencies
git commit -m "chore(deps): bump httpx from 0.26 to 0.27"

# Documentation
git commit -m "docs: add authentication example to README"

# Breaking change → 0.1.9 → 1.0.0
git commit -m "feat!: remove deprecated v1 authentication method"

# Breaking change with migration notes
git commit -m "feat(auth): replace API key with OAuth2 token

BREAKING CHANGE: ApiKeyClient removed, use OAuth2Client instead.
See the migration guide: https://github.com/dainok/netdoc/wiki/migration-v2"
```

---

## Running Unit Tests

```bash
# Run full test suite with coverage report
make test

# Run a specific test file
pytest tests/unit/test_001_normalize_base_url.py -v

# Run a specific test function
pytest tests/unit/test_001_normalize_base_url.py::test_trailing_slash -v

# Run only unit tests
pytest tests/unit/ -v

# Run with coverage and open the HTML report
pytest --cov=netdoc_sdk --cov-report=html
open htmlcov/index.html
```

The minimum required coverage is **80%**. The CI pipeline enforces this threshold
and will fail if it is not met.

---

## Running Integration Tests

A local Cisco IOS-XE device is required to run the integration tests. Create a .env file with the following information:

```text
NETDOC_DEVICE_ADDRESS='192.168.0.1'
NETDOC_DEVICE_USERNAME='admin'
NETDOC_DEVICE_PASSWORD='cisco'
```

Then run the integration tests:

```bash
# Run integration tests
pytest pytest tests/integration -v
```

---

## Code Quality

All checks are configured in `pyproject.toml` and run automatically on commit
via `pre-commit`. You can also run them manually:

```bash
# Run all hooks on all files (same as CI)
make check

# Run only the linter with autofix
ruff check . --fix

# Run only the formatter
ruff format .

# Run type checking
mypy src/

# Run security analysis
bandit -c pyproject.toml -r src/
```

### Tools in use

| Tool | Purpose |
|---|---|
| `ruff` | Linting and formatting (replaces flake8, black, isort, pyupgrade) |
| `mypy` | Static type checking |
| `bandit` | Security analysis |
| `markdownlint` | Markdown linting |
| `pre-commit` | Runs all of the above automatically on commit |

---

## Releasing

Releases are fully automated. As a contributor you do not need to manage
version numbers or changelogs manually.

### How it works

1. Every merge to `main` triggers `release-please`
2. It analyses commits since the last release and determines the next version
   according to Conventional Commits:
   - `fix:` → patch bump (`0.1.9 → 0.1.10`)
   - `feat:` → minor bump (`0.1.9 → 0.2.0`)
   - `feat!:` or `BREAKING CHANGE` footer → major bump (`0.1.9 → 1.0.0`)
3. `release-please` opens or updates a release pull request with:
   - Updated version in `pyproject.toml`
   - Updated `CHANGELOG.md`
4. When the release pull request is merged, the CD pipeline:
   - Creates the git tag (e.g. `v0.1.10`)
   - Publishes the GitHub Release with release notes
   - Builds the wheel and sdist
   - Uploads the package to PyPI

> **Note:** `chore:`, `docs:`, `test:`, `ci:`, and `refactor:` commits do not
> trigger a version bump on their own. They are included in the changelog under
> the next release caused by a `feat:` or `fix:` commit.
