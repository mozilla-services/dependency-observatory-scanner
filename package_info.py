#!/usr/bin/env python

import json
import os
import os.path
from collections import defaultdict
from subprocess import check_output, CalledProcessError


def text_output(*args, **kwargs):
    """Calls command and returns stripped UTF8 stdout"""
    return check_output(*args, **kwargs).decode("utf-8").strip()


def read_version_json():
    """
    Read the dockerflow version.json object:
    https://github.com/mozilla-services/Dockerflow/blob/master/docs/version_object.md
    """
    with open("version.json", "r") as fin:
        return json.load(fin)


def text_output_with_returncode(*args, **kwargs):
    """
    Calls command, returns tuple of return code and stripped UTF8 stdout output.

    NB: catches subprocess call failures
    """
    try:
        return (0, text_output(*args, **kwargs))
    except CalledProcessError as e:
        return e.returncode, e.output.decode("utf-8").strip()


def find_js_files():
    """
    Finds JS package and lock files and returns a list of paths to
    those files including filename
    """
    # NB: use one pattern for package files since yarn uses "package.json" too
    return text_output(
        "find -not \( -path node_modules/ -prune \) -name 'yarn\.lock|(package|package-lock|npm-shrinkwrap)\.json'",
        shell=True,
    ).split("\n")


def group_js_files_by_path(files):
    """
    Groups JS package and lock files by dirname and returns a
    defaultdict of paths to lists of package and lock files at that path

    npm and yarn both use pkg and lock files in CWD to install
    """
    files_by_path = defaultdict(list)
    for f in files:
        # NB: dirname returns '' for .
        files_by_path[os.path.dirname(f)].append(f)
    return files_by_path


def check_js_files_at_path(filenames):
    """
    Given a set of filenames in a directory checks pkg to lock files
    are 1:N i.e. that each lock file should have a package.json and each
    package.json shoud have one or more lock files
    """
    has_package_file = "package.json" in filenames
    has_lock_file = len(filenames - set(["package.json"])) >= 1
    return has_package_file, has_lock_file


def is_yarn_dir(base_filenames):
    return "yarn.lock" in base_filenames


def get_install_command(base_filenames):
    """
    Returns npm or yarn install cmd to run for production deps.
    """
    if is_yarn_dir(base_filenames):
        args = ["yarn", "install", "--no-progress", "--production"]
    else:
        args = ["npm", "install", "--no-progress", "--production"]
    return args


def get_list_command(base_filenames):
    """
    Returns npm or yarn list cmd to run for production deps.
    """
    if is_yarn_dir(base_filenames):
        args = ["yarn", "ls", "--production", "--json", "--non-interactive"]
    else:
        # "The tree shown is the logical dependency tree, based on package
        # dependencies, not the physical layout of your node_modules folder."
        args = ["npm", "ls", "--production", "--json", "--long"]
    return args


def main():
    files = find_js_files()
    files_by_path = group_js_files_by_path(files)

    dirs = []
    for (path, files_at_path) in files_by_path.items():
        base_filenames = set([os.path.basename(f) for f in files_at_path])
        if len(base_filenames) < 1:
            raise Exception("Got path {} without any JS pkg or lock files".format(path))

        if path == "":  # fix that os.path.dirname returns '' for .
            path = "."

        has_package_file, has_lock_file = check_js_files_at_path(base_filenames)

        cmds_to_run = [
            # get_install_command(base_filenames),
            get_list_command(base_filenames)
        ]

        commands = []
        # run each command suppressing stderr. and save the return code and stdout
        for cmd in cmds_to_run:
            with open(
                os.devnull, "w"
            ) as devnull:  # NB: on Python 3 can use subprocess.DEVNULL
                exit_code, output = text_output_with_returncode(
                    cmd, cwd=path, stderr=devnull
                )
            commands.append(dict(cmd=cmd, exit_code=exit_code, stdout=output))

        dirs.append(
            dict(
                path=path,
                has_package_file=has_package_file,
                has_lock_file=has_lock_file,
                commands=commands,
            )
        )

    print(
        json.dumps(
            dict(
                lang_versions=dict(
                    python=text_output(
                        [
                            "python",
                            "-c",
                            "import platform; print(platform.python_version())",
                        ]
                    ),
                    node=text_output(["node", "--version"]),
                ),
                pkg_manager_versions=dict(
                    yarn=text_output(["yarn", "--version"]),
                    npm=text_output(["npm", "--version"]),
                ),
                version_json=read_version_json(),
                dirs=dirs,
            ),
            indent=4,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
