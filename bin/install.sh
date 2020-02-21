#!/usr/bin/env bash

set -ev
test -d venv || python -m venv venv

echo "installing"

DEV=${DEV:-"0"}

(source venv/bin/activate && \
     pip install --no-cache-dir --upgrade pip && \
     pip install --no-cache-dir --require-hashes -r requirements.txt.lock)

if [ "$DEV" = "1" ]; then
   (source venv/bin/activate && pip install --no-cache-dir --require-hashes -r dev-requirements.txt.lock)
fi
