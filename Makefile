# Chirp Makefile
# Worktree onboarding: make install (uses .python-version + config/python.env)

VENV_DIR ?= .venv
ENV_FILE ?= config/python.env
UV_RUN = uv run --env-file $(ENV_FILE)

.PHONY: all help install test lint format ty preflight site-serve site-build bengal clean build publish release gh-release changelog changelog-draft changelog-check

all: help

help:
	@echo "Chirp Development CLI"
	@echo "====================="
	@echo "Python pin: $$(cat .python-version 2>/dev/null || echo '3.14t (missing .python-version)')"
	@echo "Runtime env: $(ENV_FILE)"
	@echo ""
	@echo "New worktree / fresh clone:"
	@echo "  make install     - create .venv from .python-version and sync dev + docs deps"
	@echo ""
	@echo "Daily commands:"
	@echo "  make test        - run the test suite"
	@echo "  make lint        - run ruff linter"
	@echo "  make format      - run ruff formatter"
	@echo "  make ty          - run ty type checker"
	@echo "  make preflight   - fast pre-push invariants"
	@echo "  make site-serve  - Bengal dev server (http://127.0.0.1:5173)"
	@echo "  make site-build  - build docs site locally"
	@echo "  make bengal s    - any Bengal subcommand (e.g. make bengal ARGS='s')"
	@echo ""
	@echo "Release:"
	@echo "  make changelog / changelog-draft / changelog-check"
	@echo "  make build / publish / release / gh-release"
	@echo ""
	@echo "  make clean       - remove venv, build artifacts, and caches"

# One command for every new Conductor worktree or fresh clone.
# .python-version selects 3.14t; config/python.env is applied by site/bengal wrappers.
install:
	@echo "Syncing dependencies (Python pin: $$(cat .python-version))..."
	uv sync --group dev --group docs
	@echo "✓ Ready. Run: make site-serve  (or: cd site && ./bengal s)"

test:
	$(UV_RUN) pytest -q --tb=short

lint:
	$(UV_RUN) ruff check .

format:
	$(UV_RUN) ruff format .

ty:
	$(UV_RUN) ty check src/chirp/

preflight:
	$(UV_RUN) poe preflight

site-serve:
	./scripts/bengal-site serve --environment local

site-build:
	./scripts/bengal-site build --environment local

# Usage: make bengal ARGS="s"   or   make bengal ARGS="build --environment local"
bengal:
	@test -n "$(ARGS)" || (echo "Usage: make bengal ARGS='s'"; exit 1)
	./scripts/bengal-site $(ARGS)

# =============================================================================
# Build & Release
# =============================================================================

changelog:
	@echo "Compiling changelog from fragments..."
	$(UV_RUN) towncrier build --yes

changelog-draft:
	$(UV_RUN) towncrier build --draft

changelog-check:
	$(UV_RUN) towncrier check --compare-with origin/main

build:
	@echo "Building distribution packages..."
	rm -rf dist/
	uv build --out-dir dist/
	@echo "✓ Built:"
	@ls -la dist/

publish:
	@echo "Publishing to PyPI..."
	@if [ -f .env ]; then \
		export $$(cat .env | xargs) && uv publish; \
	else \
		echo "Warning: No .env file found, trying without token..."; \
		uv publish; \
	fi

release: changelog build publish
	@echo "✓ Release complete"

gh-release:
	@VERSION=$$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	PROJECT=$$(grep -m1 '^name = ' pyproject.toml | sed 's/name = "\(.*\)"/\1/'); \
	NOTES="site/content/releases/$$VERSION.md"; \
	if [ ! -f "$$NOTES" ]; then echo "Error: $$NOTES not found"; exit 1; fi; \
	echo "Creating release v$$VERSION for $$PROJECT..."; \
	git push origin main 2>/dev/null || true; \
	git push origin v$$VERSION 2>/dev/null || true; \
	awk '/^---$$/{c++;next}c>=2' "$$NOTES" \
		| grep -v '^### \(Added\|Changed\|Deprecated\|Removed\|Fixed\|Security\)' \
		| gh release create v$$VERSION \
		--title "$$PROJECT $$VERSION" \
		-F -; \
	echo "✓ GitHub release v$$VERSION created (PyPI publish will run via workflow)"

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf $(VENV_DIR)
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ty_cache" -exec rm -rf {} + 2>/dev/null || true
