#!/usr/bin/env bash

set -e

# analyze an npm package

# args:
#
# name the npm package name
# package_version the npm package version (optional defaults to all versions)
package_name=$1  # e.g. @hapi/hapi
package_version=$2  # e.g. 19.1.1

# the optional env vars:
#
# IMAGE_NAME specifies which docker image to run. Defaults to "mozilla/dependencyscan:latest" (use "fpr:build" for a local image build)
#
IMAGE_NAME=${IMAGE_NAME:-"mozilla/dependencyscan:latest"}

# optionally add --docker-pull --docker-build --save-to-tmpfile to
# find_git_refs, find_dep_files, run_repo_tasks steps below

if [[ ${package_version:=""} = "" ]]; then
    echo "analyzing all versions of ${package_name}"
    printf '{"name":"%s"}\n' "$package_name" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  fetch_package_data fetch_npm_registry_metadata | tee "package_npm_registry_meta.jsonl" \
    | jq -c '.versions[] | {package_name: .name, package_version: .version, org: (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | first), repo:  (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | last), repo_url: (.repository.url| sub("git"; "https")), ref: {kind: "commit", value: .gitHead}}' \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  find_dep_files --keep-volumes | tee "package_dep_files.jsonl" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  run_repo_tasks --keep-volumes --language nodejs --package-manager npm --dir './' --repo-task install --repo-task list_metadata --repo-task audit | tee "package_repo_tasks.jsonl" \
    | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v  postprocess --repo-task list_metadata --repo-task audit | tee "package_postprocessed_repo_tasks.jsonl" \
    | docker run --rm -i --net=host "${IMAGE_NAME}" python fpr/run_pipeline.py -v save_to_db --input-type postprocessed_repo_task
else
    echo "analyzing ${package_name}@${package_version}"
    printf '{"name":"%s"}\n' "$package_name" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  fetch_package_data fetch_npm_registry_metadata | tee "package_npm_registry_meta.jsonl" \
    | jq -c '.versions[] | {package_name: .name, package_version: .version, org: (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | first), repo:  (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | last), repo_url: (.repository.url| sub("git"; "https")), ref: {kind: "commit", value: .gitHead}}' \
    | jq -c "select(.package_version == \"${package_version}\")" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  find_dep_files --keep-volumes | tee "package_dep_files.jsonl" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v  run_repo_tasks --keep-volumes --language nodejs --package-manager npm --dir './' --repo-task install --repo-task list_metadata --repo-task audit | tee "package_repo_tasks.jsonl" \
    | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v  postprocess --repo-task list_metadata --repo-task audit | tee "package_postprocessed_repo_tasks.jsonl" \
    | docker run --rm -i --net=host "${IMAGE_NAME}" python fpr/run_pipeline.py -v save_to_db --input-type postprocessed_repo_task
fi
