PYTHON ?= python3

.PHONY: check test docs lint
check: docs lint test

test:
	$(PYTHON) -m unittest discover -s tests -v

docs:
	$(PYTHON) scripts/check-docs.py

lint:
	shellcheck scripts/*.sh
