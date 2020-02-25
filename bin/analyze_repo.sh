#!/usr/bin/env bash

set -e

# analyze npm and rust deps in a git repo

# args:
#
repo_url=$1  # e.g.

# the optional env vars:
#
# IMAGE_NAME specifies which docker image to run. Defaults to "mozilla/dependencyscan:latest" (use "fpr:build" for a local image build)
#
IMAGE_NAME=${IMAGE_NAME:-"mozilla/dependencyscan:latest"}

echo "analyzing tags of ${repo_url}"
printf '{"repo_url": "%s"}\n' "${repo_url}" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_git_refs | tee "repo_tags.jsonl" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_dep_files | tee "repo_dep_files.jsonl" \
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v run_repo_tasks --docker-pull --docker-build --repo-task list_metadata --repo-task audit | tee "repo_tasks.jsonl" \
        | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v postprocess --repo-task list_metadata --repo-task audit | tee "repo_postprocessed_tasks.jsonl"
	| docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v rust_changelog | tee "repo_changelog.jsonl"
