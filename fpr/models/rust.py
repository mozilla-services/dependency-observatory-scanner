import logging
from dataclasses import asdict, dataclass, field
import enum
from typing import Dict, Tuple, Sequence, List, Optional

from fpr.serialize_util import extract_fields, get_in

log = logging.getLogger("fpr.models.rust")


@dataclass
class RustPackageID:
    """RustPackageID represents a Crate name, version, and url

    e.g. 'libc 0.2.51 (registry+https://github.com/rust-lang/crates.io-index)'

    url should match:
    https://doc.rust-lang.org/cargo/reference/pkgid-spec.html
    relevant code:
    https://github.com/rust-lang/cargo/blob/eebd1da3a89e9c7788d109b3e615e1e25dc2cfcd/src/cargo/core/package_id_spec.rs#L29
    https://github.com/rust-lang/cargo/blob/eebd1da3a89e9c7788d109b3e615e1e25dc2cfcd/src/cargo/core/package_id.rs
    https://github.com/rust-lang/cargo/blob/eebd1da3a89e9c7788d109b3e615e1e25dc2cfcd/src/cargo/core/package.rs
    """

    name: str
    version: Optional[str]
    source: Optional[str]

    @staticmethod
    def parse(spec: str) -> "RustPackageID":
        name, version, source = spec.split(" ", 3)
        source = source.strip("()")
        return RustPackageID(name, version, source)

    @property
    def crates_io_metadata_url(self) -> Optional[str]:
        # e.g. registry+https://github.com/rust-lang/crates.io-index
        # or path+file:///repo/channelserver
        if not (self.source and self.source.startswith("registry+")):
            return None
        return "https://crates.io/api/v1/crates/{}".format(self.name)


@dataclass
class RustCrate:
    """RustCrate represents a Rust dependency resolved for the given
    features. A .resolve.nodes entry from `cargo metadata` output.

    deps is the list of its resolved dependencies.
    """

    # The Package ID of this node.
    # e.g. "my-package 0.1.0 (path+file:///path/to/my-package)'
    id: str

    # The dependencies of this package, an array of Package IDs.
    # e.g. "bitflags 1.0.4 (registry+https://github.com/rust-lang/crates.io-index)"
    # dependencies: List[str]

    # The dependencies of this package. This is an alternative to
    # "dependencies" which contains additional information. In
    # particular, this handles renamed dependencies.
    #
    # e.g.
    # {
    #      /* The name of the dependency's library target.
    #      If this is a renamed dependency, this is the new
    #      name.
    #      */
    #      "name": "bitflags",
    #      /* The Package ID of the dependency. */
    #      "pkg": "bitflags 1.0.4 (registry+https://github.com/rust-lang/crates.io-index)"
    # }
    deps: List[Dict[str, str]] = field(default_factory=list)

    # Array of features enabled on this package. Affects the resolved deps.
    # e.g. ["default"]
    features: List[str] = field(default_factory=list)

    @property
    def package_id(self):
        return RustPackageID.parse(self.id)


@dataclass
class RustPackage:
    """RustPackage represents an unresolved Rust dependency

    A .packages entry from `cargo metadata` output.

    https://doc.rust-lang.org/cargo/commands/cargo-metadata.html
    """

    # The name of the package. e.g. "my-package"
    name: str
    # The version of the package. e.g. "0.1.0"
    version: str
    # The RustPackage ID, a unique identifier for referring to the
    # package. e.g. "my-package 0.1.0 (path+file:///path/to/my-package)"
    id: str
    # The license value from the manifest, or null. e.g. "MIT/Apache-2.0"
    license: Optional[str]
    # The license-file value from the manifest, or null. e.g. "LICENSE"
    license_file: Optional[str]
    # The description value from the manifest, or null. e.g. "Package description."
    description: Optional[str]
    # The source ID of the package. This represents where a package is retrieved from.
    # This is null for path dependencies and workspace members.
    # For other dependencies, it is a string with the format:
    # - "registry+URL" for registry-based dependencies.
    #   Example: "registry+https://github.com/rust-lang/crates.io-index"
    # - "git+URL" for git-based dependencies.
    #   Example: "git+https://github.com/rust-lang/cargo?rev=\
    # 5e85ba14aaa20f8133863373404cb0af69eeef2c#5e85ba14aaa20f8133863373404cb0af69eeef2c"
    source: str

    # Array of dependencies declared in the package's manifest.
    # "dependencies": [
    #     {
    #         # The name of the dependency.
    #         "name": "bitflags",
    #         # The source ID of the dependency. May be null, see description for the package source.
    #         "source": "registry+https://github.com/rust-lang/crates.io-index",
    #         # The version requirement for the dependency.
    #         # Dependencies without a version requirement have a value of "*".
    #         "req": "^1.0",
    #         # The dependency kind. "dev", "build", or null for a normal dependency.
    #         "kind": null,
    #         # If the dependency is renamed, this is the new name for the dependency as a string.
    #         # null if it is not renamed.
    #         "rename": null,
    #         # Boolean of whether or not this is an optional dependency.
    #         "optional": false,
    #         # Boolean of whether or not default features are enabled.
    #         "uses_default_features": true,
    #         # Array of features enabled.
    #         "features": [],
    #         # The target platform for the dependency.
    #            null if not a target dependency.

    #         "target": "cfg(windows)",
    #         # A string of the URL of the registry this dependency is from.
    #            If not specified or null, the dependency is from the default
    #            registry (crates.io).

    #         "registry": null
    #     }
    # ],
    dependencies: Sequence[Dict]

    # Array of Cargo targets.
    # # Array of target kinds.
    #    - lib targets list the `crate-type` values from the
    #      manifest such as "lib", "rlib", "dylib",
    #      "proc-macro", etc. (default ["lib"])
    #    - binary is ["bin"]
    #    - example is ["example"]
    #    - integration test is ["test"]
    #    - benchmark is ["bench"]
    #    - build script is ["custom-build"]
    # "kind": ["bin"],
    # Array of crate types.
    # - lib and example libraries list the `crate-type` values
    #   from the manifest such as "lib", "rlib", "dylib",
    #   "proc-macro", etc. (default ["lib"])
    # - all other target kinds are ["bin"]
    # "crate_types": ["bin"],
    # The name of the target.
    # "name": "my-package",
    # Absolute path to the root source file of the target.
    # "src_path": "/path/to/my-package/src/main.rs",
    # The Rust edition of the target. Defaults to the package edition.
    # "edition": "2018",
    # Array of required features. This property is not included if no required features are set.
    # "required-features": ["feat1"]
    targets: Sequence[Dict]

    # Set of features defined for the package. Each feature maps to an array of features or dependencies it enables.
    # "features": {
    #     "default": [
    #         "feat1"
    #     ],
    #     "feat1": [],
    #     "feat2": []
    # },
    features: Dict[str, Sequence[str]]

    # Absolute path to this package's manifest. e.g. "/path/to/my-package/Cargo.toml"
    manifest_path: str

    # Array of authors from the manifest. Empty array if no authors specified.
    #     "authors": [
    #         "Jane Doe <user@example.com>"
    #     ],
    authors: Sequence[str] = field(default_factory=list)

    # Array of categories from the manifest.
    #     "categories": [
    #         "command-line-utilities"
    #     ],
    categories: Sequence[str] = field(default_factory=list)

    # The default edition of the package. Note that individual targets may have different editions. e.g. "2018"
    edition: Optional[str] = field(default=None)

    # Array of keywords from the manifest.
    #     "keywords": [
    #         "cli"
    #     ],
    keywords: Sequence[str] = field(default_factory=list)

    # Optional string that is the name of a native library the package is linking to. e.g. "links": null
    links: Optional[str] = field(default=None)

    # Package metadata. This is null if no metadata is specified.
    #     "metadata": {
    #         "docs": {
    #             "rs": {
    #                 "all-features": true
    #             }
    #         }
    #     },
    metadata: Optional[Dict] = field(default=None)

    # The readme value from the manifest or null if not specified. e.g. "README.md"
    readme: Optional[str] = field(default=None)

    #  The repository value from the manifest or null if not specified. e.g. "https://github.com/rust-lang/cargo"
    repository: Optional[str] = field(default=None)


def cargo_metadata_to_rust_crates(cargo_meta_out: Dict,) -> Dict[str, RustCrate]:
    assert (
        get_in(cargo_meta_out, ["metadata", "version"]) == 1
    ), "cargo metadata format was not version 1"
    # build hashmap by pkg_id so we can lookup additional package info from
    # resolved crate as packages[crate.id]
    crates: Dict[str, RustCrate] = {}
    for n in get_in(cargo_meta_out, ["metadata", "nodes"]):
        crate = RustCrate(**extract_fields(n, {"id", "features", "deps"}))
        assert crate.id not in crates
        crates[crate.id] = crate
    return crates


def cargo_metadata_to_rust_crate_and_packages(
    cargo_meta_out: Dict,
) -> Tuple[Dict[str, RustCrate], Dict[str, RustPackage]]:
    log.debug(
        "running crate-graph on {0[cargo_tomlfile_path]} in {0[org]}/{0[repo]} at {0[commit]} ".format(
            cargo_meta_out
        )
    )
    crates = cargo_metadata_to_rust_crates(cargo_meta_out)

    packages: Dict[str, RustPackage] = {}
    for p in get_in(cargo_meta_out, ["metadata", "packages"]):
        pkg = RustPackage(**p)
        assert pkg.id not in packages
        packages[pkg.id] = pkg

    return (crates, packages)
