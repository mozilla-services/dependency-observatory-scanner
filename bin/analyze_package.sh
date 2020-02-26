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
# DB_URL the postgres database URL
# IMAGE_NAME specifies which docker image to run. Defaults to "mozilla/dependencyscan:latest" (use "fpr:build" for a local image build)
#
DB_URL=${DB_URL:-"postgresql+psycopg2://postgres:postgres@localhost/dependency_observatory"}
IMAGE_NAME=${IMAGE_NAME:-"mozilla/dependencyscan:latest"}

TMP_DIR=$(mktemp -d "/tmp/dep-obs.XXXXXXXXXXXX")

# optionally add --docker-pull --docker-build --save-to-tmpfile to
# find_git_refs, find_dep_files, run_repo_tasks steps below

if [[ ${package_version:=""} = "" ]]; then
    echo "analyzing all versions of ${package_name} saving intermediate results to ${TMP_DIR}"
    printf '{"name":"%s"}\n' "$package_name" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v fetch_package_data fetch_npm_registry_metadata | tee "${TMP_DIR}/package_npm_registry_meta.jsonl" \
    | jq -c '.versions[] | {package_name: .name, package_version: .version, org: (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | first), repo:  (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | last), repo_url: (.repository.url| sub("git"; "https")), ref: {kind: "commit", value: .gitHead}}' \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_dep_files --docker-pull --docker-build | tee "${TMP_DIR}/package_dep_files.jsonl" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v run_repo_tasks --docker-pull --docker-build --language nodejs --package-manager npm --dir './' --repo-task install --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/package_repo_tasks.jsonl" \
    | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v postprocess --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/package_postprocessed_repo_tasks.jsonl" \
    | docker run --rm -i --env DB_URL --net=host "${IMAGE_NAME}" python fpr/run_pipeline.py -v save_to_db --create-tables --input-type postprocessed_repo_task
else
    echo "analyzing ${package_name}@${package_version} saving intermediate results to ${TMP_DIR}"
    printf '{"name":"%s"}\n' "$package_name" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v fetch_package_data fetch_npm_registry_metadata | tee "${TMP_DIR}/package_npm_registry_meta.jsonl" \
    | jq -c '.versions[] | {package_name: .name, package_version: .version, org: (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | first), repo:  (.repository.url | sub("git://github.com/"; "") | sub(".git"; "") | split("/") | last), repo_url: (.repository.url| sub("git"; "https")), ref: {kind: "commit", value: .gitHead}}' \
    | jq -c "select(.package_version == \"${package_version}\")" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v find_dep_files --docker-pull --docker-build | tee "${TMP_DIR}/package_dep_files.jsonl" \
    | docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock "${IMAGE_NAME}" python fpr/run_pipeline.py -v run_repo_tasks  --docker-pull --docker-build --language nodejs --package-manager npm --dir './' --repo-task install --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/package_repo_tasks.jsonl" \
    | docker run --rm -i "${IMAGE_NAME}" python fpr/run_pipeline.py -v postprocess --repo-task list_metadata --repo-task audit | tee "${TMP_DIR}/package_postprocessed_repo_tasks.jsonl" \
    | docker run --rm -i --env DB_URL --net=host "${IMAGE_NAME}" python fpr/run_pipeline.py -v save_to_db --create-tables --input-type postprocessed_repo_task
fi
