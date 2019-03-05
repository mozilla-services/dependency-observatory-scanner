#!/usr/bin/env bash


# NB: can run lang checks concurrently, but add lang to tag

BASE_DOCKER_IMAGE="node:8@sha256:a8a9d8eaab36bbd188612375a54fb7f57418458812dabd50769ddd3598bc24fc"
GIT_REPO="https://github.com/mozilla/fxa-auth-server.git"
# "https://github.com/mozilla/testpilot.git"
# "https://github.com/mozilla/fxa-auth-server.git"
GIT_DIR=$(basename $GIT_REPO .git)

BUILT_REPO="${GIT_DIR}"
BUILT_TAG="latest"
BUILT_IMAGE="${BUILT_REPO}:${BUILT_TAG}"

docker images --format "{{.Repository}}:{{.Tag}}" | grep $BUILT_IMAGE > /dev/null
ALREADY_BUILT=$?


# want to answer:
# for all: how and when was that determined?
# output: [service, repo, repo commit, repo tag (if any), analysis tool version, datetime.now]
# where analysis tool version should allow us to find the version of the code it ran and the envs it picked

# where are the requirements and lock files?
# output the array [path to file, format<lang and dep or lockfile>]

# for lang in "js" "python"; do
#     echo $lang
# done;


if [[ $ALREADY_BUILT -ne "0" ]]; then
    echo "building"
    docker build \
    	   --file Dockerfile \
    	   --build-arg BASE_IMAGE=$BASE_DOCKER_IMAGE \
	   -t $BUILT_IMAGE \
	   .

    # TODO: figure out why passing git repo url as --build-arg or env var didn't work so we can skip the separate run and commit
    docker run --name ${BUILT_REPO}-wip --env GIT_REPO=$GIT_REPO -it $BUILT_IMAGE /app/bin/ensure_repo.sh
    docker commit ${BUILT_REPO}-wip $BUILT_IMAGE
    docker rm -f ${BUILT_REPO}-wip
else
    echo "already built"
    docker run -v $(pwd)/package_info.py:/app/bin/package_info.py --env GIT_REPO=$GIT_REPO --env LANG=js -it -w /app/$GIT_DIR $BUILT_IMAGE /app/bin/package_info.py
fi
