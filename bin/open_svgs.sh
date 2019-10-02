#!/usr/bin/env bash

for SVG in $(ls -1 *.svg)
do
    ./bin/in_venv.sh python -m webbrowser -t $SVG
done
