.PHONY: test test-all lint typecheck coverage watch deploy check install devcontainer

# Run focused tests fast (fail on first error)
test:
	pytest tests/ -x -q --tb=short

# Run full suite with coverage report
test-all:
	pytest tests/ \
		--cov=custom_components.omada_open_api \
		--cov-report=term-missing \
		--cov-report=html \
		-n auto

# Lint and format checks
lint:
	ruff check custom_components/ tests/
	ruff format --check custom_components/ tests/
	pylint --rcfile=pyproject.toml custom_components/omada_open_api/

# Strict type checking
typecheck:
	mypy --config-file pyproject.toml custom_components/omada_open_api/

# Open HTML coverage report
coverage:
	pytest tests/ \
		--cov=custom_components.omada_open_api \
		--cov-report=html \
		-n auto -q
	open htmlcov/index.html

# Watch mode for TDD — reruns failing tests on every file save
watch:
	ptw tests/ custom_components/ -- -x -q --tb=short

# Deploy integration to the LOCAL devcontainer HA instance and reload.
# ONLY works inside the devcontainer (requires /config and localhost:8123).
# Never deploys to a remote host.
deploy:
	bash scripts/deploy.sh

# Full quality gate (mirrors CI)
check: lint typecheck test-all

# Install / refresh dev dependencies into local venv
install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements_dev.txt
	pre-commit install

# Start the full dev environment (HA + devcontainer) from the terminal.
# Docker must be running. HA will be available at http://localhost:8123.
# The integration is mounted directly into HA — no deploy step needed for file changes.
# Use 'make deploy' only to trigger an API reload after code changes.
devcontainer:
	docker compose -f .devcontainer/docker-compose.yml up -d
	@echo "✅ HA running at http://localhost:8123"
	@echo "   Exec into devcontainer: docker compose -f .devcontainer/docker-compose.yml exec devcontainer bash"

devcontainer-down:
	docker compose -f .devcontainer/docker-compose.yml down
