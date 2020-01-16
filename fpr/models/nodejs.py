import bisect
import itertools
import logging
from dataclasses import asdict, dataclass, field
import enum
from typing import Dict, Tuple, Sequence, List, Optional, Generator, Union

from fpr.serialize_util import extract_fields, get_in, JSONPath, JSONPathElement

log = logging.getLogger("fpr.models.nodejs")

NPMPackageID = str


@dataclass
class NPMPackage:
    """
    NPMPackage represents a resolved npm package dependency (as from
    `npm list`)

    https://github.com/npm/registry/blob/master/docs/responses/package-metadata.md
    """

    # the package name from .dependencies.<pkg-name-key>[.dependencies[<pkg-name-key>]*
    # e.g. @babel/cli or the root package.json .name field
    name: Optional[str]

    # semver version number e.g. 4.0.0
    version: Optional[str]

    # URL (git, http, local file) of where the package was fetched
    # https://registry.npmjs.org/y18n/-/y18n-4.0.0.tgz (like a crate "source")
    resolved: Optional[str] = None

    # .from field e.g.
    # "webpack-dev-middleware@3.7.2"
    # "git://github.com/zaach/node-XMLHttpRequest.git#onerror"
    from_field: Optional[str] = None

    # only returned from `npm ls --long` output
    #
    # A detached gpg/pgp signature of <package>@<version>:<integrity> as of
    # April 16, 2018 per
    # https://blog.npmjs.org/post/172999548390/new-pgp-machinery
    #
    # previously a sha1sum (or sha512sum added in npm@5) of the downloaded tarball
    # https://blog.npmjs.org/post/172999548390/new-pgp-machinery
    # e.g.
    # sha1-2e8H3Od7mQK4o6j6SzHD4/fm6Ho=
    # sha512-r6lPcBGxZXlIcymEu7InxDMhdW0KDxpLgoFLcguasxCaJ/SOIZwINatK9KY/tf+ZrlywOKU0UDj3ATXUBfxJXA==
    integrity: Optional[str] = None

    # list of a package's .dependencies field for deduped, resolved direct child deps
    dependencies: List[NPMPackageID] = field(default_factory=list)

    @property
    def package_id(self: "NPMPackage") -> NPMPackageID:
        """
        https://github.com/npm/cli/blob/latest/lib/utils/package-id.js
        https://github.com/npm/cli/blob/latest/lib/utils/module-name.js
        """
        pkg_id = f"{self.name}"
        if self.version:
            pkg_id += f"@{self.version}"
        if self.integrity:
            pkg_id += f":{self.integrity}"
        return pkg_id

    @staticmethod
    def from_yarn_tree_line(d: Dict) -> "NPMPackage":
        """
        "yarn list --json" returns JSON lines like
        {type: "tree",
         data: {'name': 'domutils@1.1.6',
                'children': [{'name': 'domelementtype@1','color': 'dim', 'shadow': True}
               ],
               'hint': None, 'color': None, 'depth': 0
               }
         }

        NB: child name might not be fully resolved e.g. be @1, @~1.0.0, or ^4.0.0

        Returns an NPMPackage from that data dict.
        """
        name, *version = d["name"].rsplit("@", 1)
        return NPMPackage(
            name=name,
            version=version[0] if version else None,
            dependencies=[c["name"] for c in d["children"]],
        )


def is_valid_node_list_output_top_level(
    node_list_output: Optional[Dict[str, Union[Dict, str]]]
) -> bool:
    # NB: long output has more top level fields
    return bool(
        node_list_output
        and all(key in node_list_output for key in ["dependencies", "name", "version"])
    )


def is_valid_node_list_output_node(
    node_list_output: Optional[Dict[str, Union[Dict, str]]]
) -> bool:
    # NB: long output has more fields
    return bool(
        node_list_output
        and all(key in node_list_output for key in ["version", "from", "resolved"])
    )


def visit_deps(
    node_list_output: Dict[str, Union[Dict, str]]
) -> Generator[JSONPath, None, None]:
    """generator of nodes from npm list JSON output in DFS order
    returning paths to valid node deps in the JSON paths

    Child dep keys are unordered.
    """
    for path in _visit_child_deps(node_list_output, ["dependencies"]):
        if is_valid_node_list_output_node(get_in(node_list_output, path)):
            yield path

    if is_valid_node_list_output_top_level(node_list_output):
        yield []


def _visit_child_deps(
    node_list_output: Dict[str, Union[Dict, str]], path: JSONPath
) -> Generator[JSONPath, None, None]:
    output = get_in(node_list_output, path)
    if output:
        for child_dep_key, child_dep in output.items():
            for nested_child_path in _visit_child_deps(
                node_list_output, list(path) + [child_dep_key, "dependencies"]
            ):
                yield nested_child_path
            yield list(path) + [child_dep_key]
        yield path


def _get_pkg(d: Dict[str, str], d_key: Optional[str] = None) -> NPMPackage:
    if d_key is None:
        assert d.get("name")
    else:
        assert d_key
    return NPMPackage(
        name=d_key or d.get("name"),
        version=d.get("version", None),
        resolved=d.get("resolved", None),
        from_field=d.get("from", None),
    )


def flatten_deps(
    node_list_output: Dict[str, Union[Dict, str]]
) -> Generator[NPMPackage, None, None]:
    """returns a DFS of npm list JSON output yield NPMPackage objs with

    parent to child refs by ID
    """
    pkgs: List[NPMPackage] = []
    paths: List[JSONPath] = []
    for path in visit_deps(node_list_output):
        pkg: NPMPackage
        if path:
            assert isinstance(path[-1], str)
            pkg = _get_pkg(get_in(node_list_output, path), path[-1])
        else:
            pkg = _get_pkg(get_in(node_list_output, path))

        for prev_pkg, prev_pkg_path in itertools.zip_longest(
            reversed(pkgs), reversed(paths)
        ):
            # match direct deps as one level deeper with a matching prefix
            # e.g. from ["dependencies", "yargs"]
            # match ["dependencies", "yargs", "dependencies", "yarg-parser"]
            # but do not match:
            # [] (the root)
            # ["dependencies", "ps"] (a sibling dep)
            # or ["dependencies", "yargs", "dependencies", \
            #        "yarg-parser", "dependencies", "yarg-parser-dep"] (an indirect child)
            if (
                len(prev_pkg_path) - 2 == len(path)
                and path == prev_pkg_path[: len(path)]
            ):
                bisect.insort(pkg.dependencies, prev_pkg.package_id)

        yield pkg
        pkgs.append(pkg)
        paths.append(path)
