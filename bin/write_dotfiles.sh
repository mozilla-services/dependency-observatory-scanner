#!/usr/bin/env bash

set -e

while IFS='$\n' read -r line; do
    echo -n "$line" | jq -r '.crate_graph_pdot' > "$(echo -n "$line" | jq -r '.dot_filename')"
done
