# Common tasks for developing and releasing ouch. Run `make help` for the list.
# Every target works without make: see docs/versioning-and-releases.md for the raw commands.

PYTHON  ?= python3
RELKIT  := $(PYTHON) scripts/relkit.py
BASE    ?= origin/main

.DEFAULT_GOAL := help
.PHONY: help install test data validate versions check package release-plan notes clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install ouch with dev dependencies, and the git hooks
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) -m pre_commit install --install-hooks -t pre-commit -t pre-push

test: ## Run the test suite (incl. golden fixtures)
	$(PYTHON) -m pytest -q

data: ## Schema-check the shipped tax data
	ouch data validate

validate: ## Check the version, pyproject wiring and CHANGELOG.md
	$(RELKIT) validate

versions: ## Check the version bump against BASE (default origin/main)
	$(RELKIT) check-versions --base $(BASE)

check: validate versions test data ## Everything CI runs on a pull request

package: ## Build the sdist and wheel into dist/
	$(RELKIT) package

release-plan: ## Show what the next merge to main would release
	$(RELKIT) release --dry-run

notes: ## Print the changelog section for the current version
	$(RELKIT) notes

clean: ## Remove build output and caches
	rm -rf dist build .pytest_cache *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
