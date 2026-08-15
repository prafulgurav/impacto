.PHONY: help install fixtures test lint run demo calibrate docker clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

install:  ## install the package with dev extras
	pip install -e ".[dev]"

fixtures:  ## regenerate the deterministic demo corpus
	python scripts/generate_fixtures.py

test:  ## run the full hermetic test suite
	python -m pytest tests -q

lint:  ## ruff check
	ruff check src tests scripts

run:  ## serve the API and dashboard on :8000
	python -m impacto.cli serve --reload

demo:  ## print a digest and a worked example to stdout
	@python -m impacto.cli archetypes
	@python -m impacto.cli digest
	@python -m impacto.cli analogs US_IMMIGRATION_VISA_TIGHTENING NIFTY_IT --window "T+0..T+10"

calibrate:  ## score every encoded prior against realised history
	python -m impacto.cli calibrate

docker:  ## build the container
	docker build -t impacto:latest .

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
