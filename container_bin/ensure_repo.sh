#!/usr/bin/env bash

$GIT_REPO=${GIT_REPO:?}

GIT_DIR=$(basename $GIT_REPO .git)

cd /app
if [[ ! -d "$GIT_DIR" ]]; then
    echo "is not dir cloning"
    git clone "$GIT_REPO"
fi
cd "/app/${GIT_DIR}"
