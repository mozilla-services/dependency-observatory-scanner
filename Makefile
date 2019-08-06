
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

test-clear-cache:
	pytest --cache-clear -vv --cov=fpr/ fpr/ tests/

coverage: test
	coverage html
	python -m webbrowser htmlcov/index.html

clean:
	rm -rf htmlcov/
	docker container prune -f

run-cargo-audit:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver.csv

run-cargo-audit-and-save:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver.csv -o output.jsonl

run-cargo-metadata:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_metadata tests/fixtures/mozilla_services_channelserver.csv

run-cargo-metadata-and-save:
	PYTHONPATH=$$PYTHONPATH:fpr/ python fpr/run_pipeline.py cargo_metadata tests/fixtures/mozilla_services_channelserver.csv -o output.jsonl

update-pipenv:
	pipenv update

update-requirements:
	pipenv lock -r > requirements.txt
	pipenv lock -r --dev > dev-requirements.txt

.PHONY: coverage format type-check style-check test test-clear-cache clean install install-dev-tools run-cargo-audit run-cargo-audit-and-save run-cargo-metadata run-cargo-metadata-and-save update-pipenv update-requirements
