#!/usr/bin/env bash

set -ev

# clean the venv so we only install latest requirements
rm -rf venv requirements.txt.lock
python -m venv venv

./bin/in_venv.sh pip install -r requirements.txt
touch requirements.txt.lock
# TODO: figure out a cleaner way to pass these
# shellcheck disable=SC2046
./bin/in_venv.sh hashin --verbose --python-version 3.8 --requirements-file=requirements.txt.lock $(./bin/in_venv.sh pip freeze | tr '\n' ' ')

# clean the venv so we only install dev requirements
rm -rf venv dev-requirements.txt.lock
python -m venv venv

./bin/in_venv.sh pip install -r dev-requirements.txt
touch dev-requirements.txt.lock
# shellcheck disable=SC2046
./bin/in_venv.sh hashin --verbose --python-version 3.8 --requirements-file=dev-requirements.txt.lock $(./bin/in_venv.sh pip freeze | tr '\n' ' ')
