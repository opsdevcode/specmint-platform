CUE_VERSION := 0.17.1
PYTHON ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: format lint typecheck quality security test package release-check cue-install cue-check

format:
	$(PYTHON) -m ruff format src tests scripts
	$(PYTHON) -m ruff check --fix src tests scripts

lint:
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts

typecheck:
	$(PYTHON) -m mypy src

quality: lint typecheck

security:
	$(PYTHON) -m bandit -r src -c pyproject.toml
	$(PYTHON) -m pip_audit --skip-editable

test:
	$(PYTHON) -m pytest -q -m "not integration"

test-integration:
	$(PYTHON) -m pytest -q -m integration

package:
	$(PYTHON) -m build --sdist --wheel

release-check:
	$(PYTHON) -c "from opsdevcode_specmint.release import first_release_tag; from opsdevcode_specmint.version import service_version; print(first_release_tag(service_version=service_version()))"

cue-install:
	bash scripts/install-cue.sh

cue-check:
	@test "$$(cat cue/VERSION)" = "$(CUE_VERSION)"
	@test "$$(grep -F 'CUE_VERSION' src/opsdevcode_specmint/pins.py | head -1 | grep -o '$(CUE_VERSION)')" = "$(CUE_VERSION)"
	@tools/cue version | grep -F "v$(CUE_VERSION)"
