#!/usr/bin/env bash

set -ev
test -d venv || python -m venv venv

echo "installing"

(source venv/bin/activate && pip install --require-hashes -r requirements.txt.lock)
DEV=${DEV:-"0"}

if [ "$DEV" = "1" ]; then
   (source venv/bin/activate && pip install --require-hashes -r dev-requirements.txt.lock)
fi
