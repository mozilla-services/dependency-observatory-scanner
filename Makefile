
IN_PIPENV := pipenv run
FPR_PYTHON := PYTHONPATH=$$PYTHONPATH:fpr/ pipenv run python


install:
	pip install -r requirements.txt

install-dev-tools:
	pip install -r dev-requirements.txt

format:
	$(IN_PIPENV) black fpr/*.py fpr/**/*.py tests/**/*.py

type-check:
	$(IN_PIPENV) pyre --source-directory fpr/ --no-saved-state --show-error-traces --search-path venv/lib/python3.7/ check

style-check:
	$(IN_PIPENV) pytest -v -o codestyle_max_line_length=120 --codestyle fpr/ tests/

test:
	$(IN_PIPENV) pytest -vv --cov=fpr/ fpr/ tests/

test-clear-cache:
	$(IN_PIPENV)  pytest --cache-clear -vv --cov=fpr/ fpr/ tests/

coverage: test
	$(IN_PIPENV) coverage html
	$(IN_PIPENV) python -m webbrowser htmlcov/index.html

clean:
	rm -rf htmlcov/ fpr-debug.log fpr-graph.png fpr-graph.svg output.dot
	docker container prune -f

run-crate-graph:
	$(FPR_PYTHON) fpr/run_pipeline.py -q crate_graph tests/fixtures/cargo_metadata_serialized.json | dot -Tsvg > fpr-graph.svg
	$(IN_PIPENV) python -m webbrowser fpr-graph.svg

run-crate-graph-and-save:
	$(FPR_PYTHON) fpr/run_pipeline.py crate_graph tests/fixtures/cargo_metadata_serialized.json -o output.dot

show-dot:
	dot -Tsvg output.dot > fpr-graph.svg
	$(IN_PIPENV) python -m webbrowser fpr-graph.svg

run-cargo-audit:
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver_branch.jsonl
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver_tag.jsonl
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver_commit.jsonl

run-cargo-audit-and-save:
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_audit tests/fixtures/mozilla_services_channelserver_branch.jsonl -o output.jsonl

run-cargo-metadata:
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_metadata tests/fixtures/mozilla_services_channelserver_branch.jsonl

run-cargo-metadata-and-save:
	$(FPR_PYTHON) fpr/run_pipeline.py cargo_metadata tests/fixtures/mozilla_services_channelserver_branch.jsonl -o output.jsonl

update-pipenv:
	pipenv update

update-requirements:
	pipenv lock -r > requirements.txt
	pipenv lock -r --dev > dev-requirements.txt

.PHONY: coverage format type-check style-check test test-clear-cache clean install install-dev-tools run-crate-graph run-crate-graph-and-save run-cargo-audit run-cargo-audit-and-save run-cargo-metadata run-cargo-metadata-and-save update-pipenv update-requirements show-dot
