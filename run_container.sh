#!/usr/bin/env bash

DOCKER_IMAGE=${DOCKER_IMAGE:?}
DOCKER_IMAGE_ESCAPED="${DOCKER_IMAGE/\//_}"

OUT_DIR=${OUT_DIR:-output}
mkdir -p $OUT_DIR

docker pull $DOCKER_IMAGE
docker inspect $DOCKER_IMAGE > "${OUT_DIR}/${DOCKER_IMAGE_ESCAPED}.docker_inspect.json"
docker run -v $(pwd)/package_info.py:/tmp/bin/package_info.py -it -w /app/ $DOCKER_IMAGE /tmp/bin/package_info.py > "${OUT_DIR}/${DOCKER_IMAGE_ESCAPED}.package_info.json"
