PYTHON ?= python3

.PHONY: check test test-render docs lint
check: docs lint test

test:
	$(PYTHON) -m unittest discover -s tests -v

# Black-box CLI acceptance tests; Python standard library only.
test-render:
	$(PYTHON) tests/test_render_cli.py

docs:
	$(PYTHON) scripts/check-docs.py

lint:
	shellcheck scripts/*.sh
