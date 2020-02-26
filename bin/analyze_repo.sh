#!/usr/bin/env bash

set -e

# analyze npm and rust deps in a git repo

# args:
#
repo_url=$1  # e.g.

# the optional env vars:
#
# DB_URL the postgres database URL
# IMAGE_NAME specifies which docker image to run. Defaults to "mozilla/dependencyscan:latest" (use "fpr:build" for a local image build)
#
DB_URL=${DB_URL:-"postgresql+psycopg2://postgres:postgres@localhost/dependency_observatory"}
IMAGE_NAME=${IMAGE_NAME:-"mozilla/dependencyscan:latest"}

TMP_DIR=$(mktemp -d "/tmp/dep-obs.XXXXXXXXXXXX")

# optionally add --docker-pull --docker-build --save-to-tmpfile to
# find_git_refs, find_dep_files, run_repo_tasks steps below

echo "analyzing tags of ${repo_url} saving intermediate results to ${TMP_DIR}"
printf '{"repo_url": "%s"}\n' "${repo_url}" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_git_refs --docker-pull --docker-build | tee "${TMP_DIR}/repo_tags.jsonl" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_dep_files --docker-pull --docker-build | tee "${TMP_DIR}/repo_dep_files.jsonl" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v run_repo_tasks --docker-pull --docker-build --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/repo_tasks.jsonl" \
        | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v postprocess --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/repo_postprocessed_tasks.jsonl" \
        | docker run --rm -i --env DB_URL --net=host "${IMAGE_NAME}" python fpr/run_pipeline.py -v save_to_db --create-tables --input-type postprocessed_repo_task
