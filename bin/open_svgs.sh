#!/usr/bin/env bash

for SVG in ./*.svg
do
    ./bin/in_venv.sh python -m webbrowser -t "$SVG"
done
