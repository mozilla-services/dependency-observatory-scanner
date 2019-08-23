
IN_PIPENV := pipenv run
FPR_PYTHON := PYTHONPATH=$$PYTHONPATH:fpr/ pipenv run python fpr/run_pipeline.py

build-image:
	docker build -t fpr:build .

run-image:
	docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-test fpr:build python fpr/run_pipeline.py -v find_git_refs < tests/fixtures/mozilla_services_channelserver_repo_url.jsonl

publish-latest:
	docker tag fpr:build gguthemoz/fpr:latest
	docker push gguthemoz/fpr:latest

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
	docker stop $(shell docker ps -f "name=dep-obs-" -f "status=running" --format "{{.ID}}") || true
	docker container prune -f

run-find-git-refs:
	$(FPR_PYTHON) find_git_refs -i tests/fixtures/mozilla_services_channelserver_repo_url.jsonl

run-find-git-refs-and-save:
	$(FPR_PYTHON) find_git_refs -i tests/fixtures/mozilla_services_channelserver_repo_url.jsonl -o output.jsonl

run-crate-graph:
	$(FPR_PYTHON) -q crate_graph -i tests/fixtures/cargo_metadata_serialized.json | dot -Tsvg > fpr-graph.svg
	$(IN_PIPENV) python -m webbrowser fpr-graph.svg

run-crate-graph-and-save:
	$(FPR_PYTHON) crate_graph -i tests/fixtures/cargo_metadata_serialized.json -o default.dot
	$(FPR_PYTHON) crate_graph --node-key name --node-label name_authors --filter dpc --filter serde -i tests/fixtures/cargo_metadata_serialized.json -o serde_authors_filtered.dot
	$(FPR_PYTHON) crate_graph --node-key name --node-label name_authors --style 'dpc:color:red' --style 'serde:shape:box' -i tests/fixtures/cargo_metadata_serialized.json -o graph-with-style-args.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_version_repository -g 'repository' -i tests/fixtures/cargo_metadata_serialized.json -o groupby-repo.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_authors -g 'author' -i tests/fixtures/cargo_metadata_serialized.json -o groupby-author.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_readme -i tests/fixtures/cargo_metadata_serialized.json -o readme-node-label.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_repository -i tests/fixtures/cargo_metadata_serialized.json -o repo-node-label.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_package_source -i tests/fixtures/cargo_metadata_serialized.json -o source-node-label.dot
	$(FPR_PYTHON) crate_graph --node-key name_version --node-label name_metadata -i tests/fixtures/cargo_metadata_serialized.json -o metadata-node-label.dot

show-dot:
	dot -O -Tsvg *.dot
	./bin/open_svgs.sh

clean-graph:
	rm -f *.dot *.svg

run-cargo-audit:
	$(FPR_PYTHON) cargo_audit -i tests/fixtures/mozilla_services_channelserver_branch.jsonl
	$(FPR_PYTHON) cargo_audit -i tests/fixtures/mozilla_services_channelserver_tag.jsonl
	$(FPR_PYTHON) cargo_audit -i tests/fixtures/mozilla_services_channelserver_commit.jsonl

run-cargo-audit-and-save:
	$(FPR_PYTHON) cargo_audit -i tests/fixtures/mozilla_services_channelserver_branch.jsonl -o output.jsonl

run-cargo-metadata:
	$(FPR_PYTHON) cargo_metadata -i tests/fixtures/mozilla_services_channelserver_branch.jsonl

run-cargo-metadata-and-save:
	$(FPR_PYTHON) cargo_metadata -i tests/fixtures/mozilla_services_channelserver_branch.jsonl -o output.jsonl

run-cargo-metadata-fxa-and-save:
	$(FPR_PYTHON) cargo_metadata -i tests/fixtures/mozilla_services_fxa_branch.jsonl -o output.jsonl

run-rust-changelog:
	$(FPR_PYTHON) rust_changelog -i tests/fixtures/mozilla_services_channelserver_tag_comparisions.jsonl

run-rust-changelog-and-save:
	$(FPR_PYTHON) rust_changelog -i  -o output.jsonl

run-repo-analysis:
	$(FPR_PYTHON) find_git_refs -i tests/fixtures/mozilla_services_channelserver_repo_url.jsonl -o mozilla_services_channelserver_tags.jsonl
	$(FPR_PYTHON) cargo_metadata -i mozilla_services_channelserver_tags.jsonl -o mozilla_services_channelserver_tags_metadata.jsonl
	$(FPR_PYTHON) rust_changelog -i mozilla_services_channelserver_tags_metadata.jsonl

integration-test: run-cargo-audit run-cargo-metadata run-crate-graph-and-save

update-pipenv:
	pipenv update

update-requirements:
	pipenv lock -r > requirements.txt
	pipenv lock -r --dev > dev-requirements.txt

.PHONY: build-image run-image coverage format type-check style-check test test-clear-cache clean install install-dev-tools run-crate-graph run-crate-graph-and-save run-cargo-audit run-cargo-audit-and-save run-cargo-metadata run-cargo-metadata-and-save update-pipenv update-requirements show-dot integration-test run-find-git-refs run-find-git-refs-and-save publish-latest
