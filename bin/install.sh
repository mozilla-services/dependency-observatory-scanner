#!/usr/bin/env bash

set -ev
test -d venv || python -m venv venv

echo "installing"

(source venv/bin/activate && pip install -r requirements.txt)
DEV=${DEV:-"0"}

if [ "$DEV" = "1" ]; then
   (source venv/bin/activate && pip install -r dev-requirements.txt)
fi
