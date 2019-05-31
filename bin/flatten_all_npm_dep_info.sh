#!/usr/bin/env bash

# run in output dir
# find_images_with_{yarn,npm}_version != null

for pkg_file in $(ls -1 *.package_info.json); do
    echo "$pkg_file"
    echo  $(jq '.lang_versions?' "$pkg_file")
    echo  $(jq '.pkg_manager_versions?' "$pkg_file")
    # echo  $(jq '.dirs[]? | length' "$pkg_file")
    # jq '.dirs[].commands[].stdout | fromjson' "$pkg_file" | ./flatten_npm_dep_info.py
done
