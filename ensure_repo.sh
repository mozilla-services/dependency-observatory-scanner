#!/usr/bin/env bash

GIT_DIR=$(basename $GIT_REPO .git)

cd /app
pwd
ls
echo "is $GIT_DIR a dir?"
if [[ ! -d "$GIT_DIR" ]]; then
    echo "is not dir cloning"
    git clone "$GIT_REPO"
fi
cd "/app/${GIT_DIR}"
git pull
