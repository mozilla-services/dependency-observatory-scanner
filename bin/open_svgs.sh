#!/usr/bin/env bash

for SVG in $(ls -1 *.svg)
do
    pipenv run python -m webbrowser -t $SVG
done
