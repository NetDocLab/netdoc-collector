# Contributing to netdoc-collector

Thank you for your interest in contributing to NetDoc Collector. This guide describes the development workflow, tooling, and conventions used in this project.

## Requirements

- Python >=3.12, <3.14
- Poetry for dependency management
- pre-commit for local quality hooks

## Local setup

```bash
# Clone the repository
git clone https://github.com/netdoclab/netdoc-collector.git
cd netdoc-collector

# Install dependencies and development hooks
poetry install
pre-commit install
pre-commit install --hook-type commit-msg

# Verify the setup
make check
```

## Project structure

```text
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── README.md
├── config-example.yaml
├── inventory-example.json
├── mkdocs.yml
├── poetry.lock
├── pyproject.toml
├── release-please-config.json
├── secrets-example.yaml
├── src
│   └── netdoc_collector
│       ├── __init__.py
│       ├── __main__.py
│       ├── core
│       │   ├── __init__.py
│       │   ├── ansible_inventory.py
│       │   ├── scanner.py
│       │   ├── tasks.py
│       │   └── utils.py
│       ├── main.py
│       └── plugins
│           ├── __init__.py
│           ├── base.py
│           ├── dispatcher.py
│           ├── netmiko_allied_telesis_awplus.py
│           ├── netmiko_aruba_oscx.py
│           ├── netmiko_cisco_ios.py
│           ├── netmiko_cisco_nxos.py
│           ├── netmiko_cisco_xr.py
│           ├── netmiko_hp_comware.py
│           ├── netmiko_hp_procurve.py
│           ├── netmiko_huawei_vrp.py
│           └── netmiko_linux.py
└── tests
```

## Development workflow

Every change should follow this flow:

1. Create a branch that reflects the scope of the change.
2. Make a focused change and add or update tests where appropriate.
3. Run the local validation checks before opening a pull request.
4. Commit using the Conventional Commits format.
5. Open a pull request against main.

### Local checks

```bash
make check
make test
```

## Commit convention

This project follows Conventional Commits. The format is:

```text
<type>[optional scope]: <short description>
```

Common types include feat, fix, chore, docs, refactor, test, ci, build, and perf.

Examples:

```bash
git commit -m "feat(scanner): add host discovery for SSH-only devices"
git commit -m "fix(tasks): handle canceled jobs gracefully"
git commit -m "docs: improve CLI usage examples"
```

## Running tests

Run the full test suite:

```bash
make test
```

Run a specific test file when debugging a targeted area:

```bash
pytest tests/unit/test_005_main.py -v
```

## Code quality

The repository uses pre-commit checks and Ruff formatting. Run the following commands locally if needed:

```bash
poetry run ruff check .
poetry run ruff format .
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
