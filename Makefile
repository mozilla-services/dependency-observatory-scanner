
IN_VENV := bash bin/in_venv.sh
FPR_PYTHON := PYTHONPATH=$$PYTHONPATH:fpr/ $(IN_VENV) python fpr/run_pipeline.py

build-image:
	docker build -t fpr:build .

run-image:
	docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-test fpr:build python fpr/run_pipeline.py -v find_git_refs < tests/fixtures/mozilla_services_channelserver_repo_url.jsonl

run-repo-analysis-in-image:
	cat tests/fixtures/mozilla_services_channelserver_repo_url.jsonl | \
		docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-find_git_refs fpr:build python fpr/run_pipeline.py find_git_refs | \
		tee channelserver_tags.jsonl | \
		docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-cargo_metadata fpr:build python fpr/run_pipeline.py cargo_metadata | \
		tee channelserver_tags_metadata.jsonl | \
		docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-rust_changelog fpr:build python fpr/run_pipeline.py rust_changelog | \
		tee channelserver_changelog.jsonl

run-diff-repo-analysis-in-image:
	CIRCLE_SHA1=5a3e3967e90d65ca0d7a17b0466a3385898c3b6b printf "{\"org\": \"mozilla-services\", \"repo\": \"syncstorage-rs\", \"ref\": {\"value\": \"master\", \"kind\": \"branch\"}, \"repo_url\": \"https://github.com/mozilla-services/syncstorage-rs.git\"}\n{\"org\": \"mozilla-services\", \"repo\": \"syncstorage-rs\", \"ref\": {\"value\": \"5a3e3967e90d65ca0d7a17b0466a3385898c3b6b\", \"kind\": \"commit\"}, \"repo_url\": \"https://github.com/mozilla-services/syncstorage-rs.git\"}\n"  | \
	    docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-cargo_metadata fpr:build python fpr/run_pipeline.py cargo_metadata | \
	    docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock --name fpr-rust_changelog fpr:build python fpr/run_pipeline.py rust_changelog

check-channelserver-repo-analysis:
	test -f channelserver_tags.jsonl
	diff channelserver_tags.jsonl tests/fixtures/channelserver_tags.jsonl
	# TODO: check the metadata too or not since it'll change as deps update?
	test -f channelserver_changelog.jsonl
	# TODO: check for equivalent JSON output (changelog output needs work though)


install:
	bash ./bin/install.sh

install-dev:
	DEV=1 bash ./bin/install.sh

format:
	$(IN_VENV) black fpr/*.py fpr/**/*.py tests/**/*.py

type-check:
	MYPYPATH=$(shell pwd)/venv/lib/python3.7/site-packages/ $(IN_VENV) mypy fpr/

style-check:
	$(IN_VENV) pytest -v -o codestyle_max_line_length=120 --codestyle fpr/ tests/

test:
	$(IN_VENV) pytest -vv --cov=fpr/ fpr/ tests/

unit-test: format style-check test type-check

test-clear-cache:
	$(IN_VENV)  pytest --cache-clear -vv --cov=fpr/ fpr/ tests/

coverage: test
	$(IN_VENV) coverage html
	$(IN_VENV) python -m webbrowser htmlcov/index.html

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
	$(IN_VENV) python -m webbrowser fpr-graph.svg

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

run-crates-io-metadata-and-save:
	$(FPR_PYTHON) crates_io_metadata -i tests/fixtures/channelserver_tags_metadata.jsonl -o output.jsonl

run-cargo-metadata-fxa-and-save:
	$(FPR_PYTHON) cargo_metadata -i tests/fixtures/mozilla_services_fxa_branch.jsonl -o output.jsonl

run-rust-changelog:
	$(FPR_PYTHON) rust_changelog -i tests/fixtures/channelserver_tags_metadata.jsonl

run-rust-changelog-and-save:
	$(FPR_PYTHON) rust_changelog -i tests/fixtures/channelserver_tags_metadata.jsonl -o output.jsonl

run-repo-analysis:
	$(FPR_PYTHON) find_git_refs -i tests/fixtures/mozilla_services_channelserver_repo_url.jsonl -o mozilla_services_channelserver_tags.jsonl
	$(FPR_PYTHON) cargo_metadata -i mozilla_services_channelserver_tags.jsonl -o mozilla_services_channelserver_tags_metadata.jsonl
	$(FPR_PYTHON) rust_changelog -i mozilla_services_channelserver_tags_metadata.jsonl

integration-test: run-cargo-audit run-cargo-metadata run-crate-graph-and-save

# NB: assuming package names don't include spaces
update-requirements:
	bash ./bin/update_requirements.sh

.PHONY: build-image run-image coverage format type-check style-check test test-clear-cache clean install install-dev-tools run-crate-graph run-crate-graph-and-save run-cargo-audit run-cargo-audit-and-save run-cargo-metadata run-cargo-metadata-and-save update-requirements show-dot integration-test run-find-git-refs run-find-git-refs-and-save publish-latest run-repo-analysis-in-image check-channelserver-repo-analysis run-diff-repo-analysis-in-image unit-test
