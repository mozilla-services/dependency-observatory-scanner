#!/usr/bin/env bash

DOCKER_PULL=${DOCKER_PULL:-"0"}
DOCKER_INSPECT=${DOCKER_INSPECT:-"0"}

DOCKER_IMAGE=${DOCKER_IMAGE:?}
DOCKER_IMAGE_ESCAPED="${DOCKER_IMAGE/\//_}"

OUT_DIR=${OUT_DIR:-output}
mkdir -p $OUT_DIR


case $1 in
    pull)
	docker pull $DOCKER_IMAGE
	;;
    inspect)
	docker inspect $DOCKER_IMAGE > "${OUT_DIR}/${DOCKER_IMAGE_ESCAPED}.docker_inspect.json"
	;;
    pkg-info)
	docker run -v $(pwd)/../container_bin/package_info.py:/tmp/bin/package_info.py:ro -it -w /app/ $DOCKER_IMAGE /tmp/bin/package_info.py > "${OUT_DIR}/${DOCKER_IMAGE_ESCAPED}.package_info.json"
	;;
    *)
	echo "Unrecognized action $1"
	exit 1
esac
