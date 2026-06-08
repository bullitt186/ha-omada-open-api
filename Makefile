.PHONY: test test-all lint typecheck coverage watch deploy check install

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

# Deploy integration to HA host and reload
deploy:
	bash scripts/deploy.sh

# Full quality gate (mirrors CI)
check: lint typecheck test-all

# Install / refresh dev dependencies into local venv
install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements_dev.txt
	pre-commit install
