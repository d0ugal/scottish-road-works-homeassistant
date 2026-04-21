RUFF_VERSION ?= 0.15.9
RUFF = docker run --rm -v "$(PWD)":/src -w /src ghcr.io/astral-sh/ruff:$(RUFF_VERSION)

.PHONY: lint format test test-integration

lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) format .

test:
	uv run --extra dev pytest tests/ --ignore=tests/integration/ -v

test-integration:
	uv run --extra integration pytest tests/integration/ -v
