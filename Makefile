.PHONY: all analysis test

all: analysis

analysis:
	python scripts/reproduce_report_artifacts.py

test:
	python -m unittest discover -s tests
