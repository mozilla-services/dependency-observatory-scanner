
install:
	pip install -r requirements.txt

install-dev-tools:
	pip install -r dev-requirements.txt

format:
	black fpr/*.py fpr/**/*.py tests/**/*.py

type-check:
	pyre --source-directory fpr/ --no-saved-state --show-error-traces --search-path venv/lib/python3.7/ check

style-check:
	pytest -v -o codestyle_max_line_length=120 --codestyle fpr/ tests/

test:
	pytest -vv --cov=fpr/ fpr/ tests/

coverage: test
	coverage html
	python -m webbrowser htmlcov/index.html

clean:
	rm -rf htmlcov/
	docker container prune -f

run:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver.csv
run-and-save:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver.csv -o output.jsonl

.PHONY: coverage format typecheck style-check test clean install install-dev-tools run
